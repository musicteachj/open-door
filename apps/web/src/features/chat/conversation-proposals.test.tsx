import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ConversationOut, ProposalOut, TurnOut } from '@/api/generated'
import { CARD_DENY } from '@/app/gallery/fixtures/timeoff'
import { DANA, toolCall } from '@/test/assistant-fixtures'
import { installFakeApi } from '@/test/fake-api'
import {
  conversationOut,
  installAssistantApi,
  onProposalAction,
  onTurn,
  openStream,
  problemResponse,
  proposalOut,
  turnOut,
} from '@/test/fake-assistant'
import { renderApp } from '@/test/render-app'
import { useChatStore } from './store'

// The confirm card in the conversation at /ask: where it sits, what Confirm and Dismiss do, and how
// the page learns the card's state (always by reading the conversation again).

const QUESTION = 'Can I take Friday the 30th off?'
const TURN = 'c0ffee00-0000-4000-8000-0000000000a1'

function bookingTurn(proposal: ProposalOut, overrides: Partial<TurnOut> = {}): TurnOut {
  return turnOut({
    id: TURN,
    question: QUESTION,
    answerText: 'Here is the request. Confirm it and Marcus Bell will review it.',
    toolCalls: [toolCall({ name: 'propose_time_off_request', inputSummary: 'type=pto' })],
    proposals: [proposal],
    ...overrides,
  })
}

const withTurn = (turn: TurnOut): ConversationOut => conversationOut({ turns: [turn] })

const executed = (extra: Partial<ProposalOut> = {}) => proposalOut({ status: 'executed', ...extra })

const confirmButton = () => screen.getByRole('button', { name: /^Confirm:/ })
const card = () => screen.findByRole('region', { name: 'Book PTO' })
const composer = () => screen.getByRole('textbox', { name: 'Ask Open Door' })

function open(conversation: ConversationOut, persona: 'priya' | 'marcus' = 'priya') {
  installFakeApi(persona)
  const api = installAssistantApi({ conversation })
  const app = renderApp({ at: '/ask' })
  return { api, ...app }
}

beforeEach(() => {
  useChatStore.setState(useChatStore.getInitialState())
})
afterEach(() => {
  vi.useRealTimers()
})

function before(a: Element, b: Element) {
  return Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)
}

describe('where the card sits', () => {
  it('draws a stored card under its message, with Confirm ready and "Show your work" under the card', async () => {
    open(withTurn(bookingTurn(proposalOut())))
    const region = await card()

    expect(confirmButton()).not.toHaveAttribute('aria-disabled')
    expect(within(region).getByText(/^Expires at \d{1,2}:\d{2}/)).toBeInTheDocument()
    const message = screen.getByText(/Here is the request\./)
    const work = screen.getByRole('button', { name: 'Show your work' })
    const feedback = document.querySelector('[data-slot="feedback"]')!
    // The card sits directly under the message, then the whole footer row: feedback, then work.
    expect(before(message, region)).toBe(true)
    expect(before(region, feedback)).toBe(true)
    expect(before(feedback, work)).toBe(true)
    // One card, however many times the page drew.
    expect(screen.getAllByRole('region', { name: 'Book PTO' })).toHaveLength(1)
  })

  it('puts the card, then the HR panel, then "Show your work" on a sensitive turn', async () => {
    open(
      withTurn(
        bookingTurn(proposalOut(), {
          escalation: {
            kind: 'sensitive',
            message: 'A person should help with this.',
            hrContact: [DANA],
          },
        }),
      ),
    )
    const region = await card()

    const panel = screen.getByRole('heading', { name: 'A person in HR handles this, not the AI' })
    const work = screen.getByRole('button', { name: 'Show your work' })
    const message = screen.getByText(/Here is the request\./)
    expect(before(message, region)).toBe(true)
    expect(before(region, panel)).toBe(true)
    expect(before(panel, work)).toBe(true)
  })

  it('names the proposal tools plainly in "Show your work" and shows no request id', async () => {
    const id = '3f2a1b4c-5d6e-4f70-8a9b-0c1d2e3f4a5b'
    const { user } = open(
      withTurn(
        bookingTurn(proposalOut(), {
          toolCalls: [
            toolCall({ name: 'check_time_off', inputSummary: 'type=pto' }),
            toolCall({ name: 'propose_time_off_decision', inputSummary: `approve request ${id}` }),
          ],
        }),
      ),
    )
    await card()

    await user.click(screen.getByRole('button', { name: 'Show your work' }))

    expect(screen.getByText('Checked your time off')).toBeInTheDocument()
    expect(screen.getByText('Prepared a confirm card')).toBeInTheDocument()
    expect(document.body.textContent).not.toContain(id)
  })
})

describe('a reload', () => {
  it.each([
    ['executed', { status: 'executed' }, /^Requested\. Marcus Bell will review it\./],
    [
      'failed',
      {
        status: 'failed',
        failure: { code: 'overlaps', text: 'You already have time off.', dates: ['2026-10-30'] },
      },
      /^Couldn’t book this: you already have time off on Friday, October 30\. Nothing was changed\./,
    ],
    [
      'dismissed',
      { status: 'canceled', canceledReason: 'dismissed' },
      /^You dismissed this\. Nothing was changed\./,
    ],
    [
      'replaced',
      { status: 'canceled', canceledReason: 'replaced' },
      /^Replaced by a newer card\. Nothing was changed\./,
    ],
    [
      'turn-incomplete',
      { status: 'canceled', canceledReason: 'turn-incomplete' },
      /answer didn’t finish\. Nothing was changed\./,
    ],
    [
      'expired',
      { status: 'expired' },
      /^This card expired after 15 minutes\. Nothing was changed\./,
    ],
  ] as [string, Partial<ProposalOut>, RegExp][])(
    'shows a stored %s card in its final state, with no buttons',
    async (_name, overrides, line) => {
      open(withTurn(bookingTurn(proposalOut(overrides))))
      await card()

      expect(screen.getByText(line)).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /^Confirm:/ })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /^Dismiss/ })).not.toBeInTheDocument()
    },
  )
})

describe('a card on a live turn', () => {
  it('waits while the answer streams, then offers Confirm once the conversation is read again', async () => {
    const stream = openStream()
    onTurn(() => stream.response())
    const { api, user } = open(conversationOut())
    await user.type(
      await screen.findByRole('textbox', { name: 'Ask Open Door' }),
      `${QUESTION}{Enter}`,
    )
    await waitFor(() => expect(useChatStore.getState().status).toBe('sending'))
    stream.push('turn.started', { turnId: TURN })
    stream.push('proposal', proposalOut({ turnRunning: true }))
    stream.push('text.delta', { text: 'Here is the request.' })

    await card()
    expect(confirmButton()).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByText('Wait for the answer to finish')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Dismiss/ })).toBeEnabled()

    // The turn ends, and the server's copy of the card no longer says its turn is running.
    api.setCurrent(withTurn(bookingTurn(proposalOut({ turnRunning: false }))))
    stream.push('turn.completed', {
      turnId: TURN,
      servedBy: 'anthropic',
      usage: { inputTokens: 1, outputTokens: 1 },
    })
    stream.close()

    await waitFor(() => expect(confirmButton()).not.toHaveAttribute('aria-disabled'))
    expect(screen.queryByText('Wait for the answer to finish')).not.toBeInTheDocument()
    expect(screen.getAllByRole('region', { name: 'Book PTO' })).toHaveLength(1)
  })

  it('shows an earlier turn’s pending card as replaced as soon as a new card arrives', async () => {
    const stream = openStream()
    onTurn(() => stream.response())
    // Both cards expire far from now, so the only read in this test is the one the new card causes.
    const expiresAt = new Date(Date.now() + 3_600_000).toISOString()
    const older = proposalOut({ id: 'c0ffee00-0000-4000-8000-0000000000b9', expiresAt })
    const earlier = bookingTurn(older, { id: 'c0ffee00-0000-4000-8000-0000000000a0' })
    const { api, user } = open(withTurn(earlier))
    expect(await screen.findByRole('button', { name: /^Confirm:/ })).toBeInTheDocument()
    await user.type(
      await screen.findByRole('textbox', { name: 'Ask Open Door' }),
      `${QUESTION}{Enter}`,
    )
    await waitFor(() => expect(useChatStore.getState().status).toBe('sending'))
    stream.push('turn.started', { turnId: TURN })

    // The server replaces a pending card across the conversation when the new one is made.
    api.setCurrent(
      withTurn(
        bookingTurn(
          { ...older, status: 'canceled', canceledReason: 'replaced' },
          { id: 'c0ffee00-0000-4000-8000-0000000000a0' },
        ),
      ),
    )
    stream.push('proposal', proposalOut({ turnRunning: true, expiresAt }))

    // Well inside the page's two-second poll: the card's arrival itself reads the conversation.
    expect(
      await screen.findByText(/^Replaced by a newer card\./, undefined, { timeout: 1000 }),
    ).toBeInTheDocument()
    // The turn is still streaming: only the new card is waiting on its answer.
    expect(screen.getAllByRole('button', { name: /^Confirm:/ })).toHaveLength(1)
  })

  it.each([
    [
      'fails',
      (stream: ReturnType<typeof openStream>) => {
        stream.push('error', {
          code: 'internal',
          message: 'Something went wrong.',
          requestId: 'r1',
        })
        stream.close()
      },
    ],
    [
      'is stopped',
      async () => {
        await userEvent.setup().click(screen.getByRole('button', { name: 'Stop' }))
      },
    ],
  ] as [string, (stream: ReturnType<typeof openStream>) => void | Promise<void>][])(
    'stops telling the card to wait for the answer once the turn %s',
    async (_ending, end) => {
      const stream = openStream()
      onTurn(() => stream.response())
      const { user } = open(conversationOut())
      await user.type(
        await screen.findByRole('textbox', { name: 'Ask Open Door' }),
        `${QUESTION}{Enter}`,
      )
      await waitFor(() => expect(useChatStore.getState().status).toBe('sending'))
      stream.push('turn.started', { turnId: TURN })
      stream.push('proposal', proposalOut({ turnRunning: true }))
      stream.push('text.delta', { text: 'Here is the request.' })
      await card()
      expect(screen.getByText('Wait for the answer to finish')).toBeInTheDocument()

      await end(stream)

      await waitFor(() => expect(useChatStore.getState().status).not.toBe('streaming'))
      // The read has not told the card anything else, and the card no longer says to wait.
      expect(screen.queryByText('Wait for the answer to finish')).not.toBeInTheDocument()
    },
  )

  it('shows the final state of a card the turn’s ending canceled, from the read', async () => {
    const stream = openStream()
    onTurn(() => stream.response())
    const { api, user } = open(conversationOut())
    await user.type(
      await screen.findByRole('textbox', { name: 'Ask Open Door' }),
      `${QUESTION}{Enter}`,
    )
    await waitFor(() => expect(useChatStore.getState().status).toBe('sending'))
    stream.push('turn.started', { turnId: TURN })
    stream.push('proposal', proposalOut({ turnRunning: true }))
    await card()

    api.setCurrent(
      withTurn(
        bookingTurn(proposalOut({ status: 'canceled', canceledReason: 'turn-incomplete' }), {
          status: 'failed',
          error: { code: 'internal', message: 'Something went wrong.' },
        }),
      ),
    )
    stream.push('error', { code: 'internal', message: 'Something went wrong.', requestId: 'r1' })
    stream.close()

    expect(
      await screen.findByText(/answer didn’t finish\. Nothing was changed\./),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Confirm:/ })).not.toBeInTheDocument()
  })
})

describe('Confirm', () => {
  it('confirms a booking with no note, then shows what the next read says', async () => {
    const { api, user } = open(withTurn(bookingTurn(proposalOut())))
    const posted = onProposalAction(() => {
      api.setCurrent(withTurn(bookingTurn(executed())))
      return HttpResponse.json(executed())
    })
    await card()

    await user.click(confirmButton())

    expect(await screen.findByText(/^Requested\. Marcus Bell will review it\./)).toBeInTheDocument()
    expect(posted).toHaveLength(1)
    expect(posted[0]).toMatchObject({ kind: 'confirm', body: null })
    expect(screen.queryByRole('button', { name: /^Confirm:/ })).not.toBeInTheDocument()
  })

  it('sends a denial’s note, and after a reload the card says the note will be seen', async () => {
    const deny = proposalOut({ action: 'timeoff.decide', card: CARD_DENY })
    const { api, user } = open(withTurn(bookingTurn(deny)), 'marcus')
    const posted = onProposalAction(() => {
      api.setCurrent(
        withTurn(bookingTurn({ ...deny, status: 'executed', deniedNote: 'Two of us are out.' })),
      )
      return HttpResponse.json({ ...deny, status: 'executed' })
    })
    await screen.findByRole('region', { name: 'Deny a request' })

    await user.type(screen.getByRole('textbox', { name: /Note to Zara/ }), 'Two of us are out.')
    await user.click(screen.getByRole('button', { name: /^Confirm: deny/ }))

    expect(
      await screen.findByText('Denied. Zara will see your note on the Time off page.'),
    ).toBeInTheDocument()
    expect(posted[0]).toMatchObject({ kind: 'confirm', body: { note: 'Two of us are out.' } })
    expect(screen.getByText('“Two of us are out.”')).toBeInTheDocument()
  })

  it('sends no note for a denial left blank', async () => {
    const deny = proposalOut({ action: 'timeoff.decide', card: CARD_DENY })
    const { user } = open(withTurn(bookingTurn(deny)), 'marcus')
    const posted = onProposalAction(() => HttpResponse.json({ ...deny, status: 'executed' }))
    await screen.findByRole('region', { name: 'Deny a request' })

    await user.click(screen.getByRole('button', { name: /^Confirm: deny/ }))

    await waitFor(() => expect(posted).toHaveLength(1))
    expect(posted[0]?.body).toBeNull()
  })

  it('shows the card calmly after a 409 executed (two tabs), never an error', async () => {
    const { api, user } = open(withTurn(bookingTurn(proposalOut())))
    const posted = onProposalAction(() => {
      api.setCurrent(withTurn(bookingTurn(executed())))
      return problemResponse(409, 'executed', 'A fixed sentence.')
    })
    await card()

    await user.click(confirmButton())

    expect(await screen.findByText(/^Requested\./)).toBeInTheDocument()
    expect(posted).toHaveLength(1)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText('A fixed sentence.')).not.toBeInTheDocument()
  })

  it('keeps the card pending and calm after a 409 turn-running, never an error', async () => {
    const { api, user } = open(withTurn(bookingTurn(proposalOut())))
    onProposalAction(() => {
      api.setCurrent(withTurn(bookingTurn(proposalOut({ turnRunning: true }))))
      return problemResponse(409, 'turn-running', 'A fixed sentence.')
    })
    await card()

    await user.click(confirmButton())

    await waitFor(() => expect(confirmButton()).toHaveAttribute('aria-disabled', 'true'))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText('A fixed sentence.')).not.toBeInTheDocument()
  })

  it('shows the card’s failure line, calmly, when the proposal is gone for this person', async () => {
    const { user } = open(withTurn(bookingTurn(proposalOut())))
    onProposalAction(() => problemResponse(404, 'not-found', 'No such proposal.'))
    await card()

    await user.click(confirmButton())

    expect(
      await screen.findByText('This card is no longer available. Nothing was changed.'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Confirm:/ })).not.toBeInTheDocument()
  })

  it('leaves the card pending with Confirm usable again after a server failure, and works on retry', async () => {
    const { api, user } = open(withTurn(bookingTurn(proposalOut())))
    let calls = 0
    onProposalAction(() => {
      calls++
      if (calls === 1) return new HttpResponse(null, { status: 500 })
      api.setCurrent(withTurn(bookingTurn(executed())))
      return HttpResponse.json(executed())
    })
    await card()

    await user.click(confirmButton())

    expect(
      await screen.findByText(/That didn’t go through\. Nothing was changed\./),
    ).toBeInTheDocument()
    await waitFor(() => expect(confirmButton()).not.toHaveAttribute('aria-busy', 'true'))
    expect(confirmButton()).toBeEnabled()

    await user.click(confirmButton())

    expect(await screen.findByText(/^Requested\./)).toBeInTheDocument()
    expect(screen.queryByText(/That didn’t go through/)).not.toBeInTheDocument()
  })
})

describe('a double click', () => {
  it('on Confirm sends one request, even when both clicks land before the page draws again', async () => {
    const { api } = open(withTurn(bookingTurn(proposalOut())))
    const posted = onProposalAction(() => {
      api.setCurrent(withTurn(bookingTurn(executed())))
      return HttpResponse.json(executed())
    })
    await card()
    const button = confirmButton()

    act(() => {
      button.click()
      button.click()
    })

    expect(await screen.findByText(/^Requested\./)).toBeInTheDocument()
    expect(posted).toHaveLength(1)
  })

  it('on Confirm and then Dismiss sends only the first', async () => {
    const { api } = open(withTurn(bookingTurn(proposalOut())))
    const posted = onProposalAction(() => {
      api.setCurrent(withTurn(bookingTurn(executed())))
      return HttpResponse.json(executed())
    })
    await card()

    act(() => {
      confirmButton().click()
      screen.getByRole('button', { name: /^Dismiss/ }).click()
    })

    expect(await screen.findByText(/^Requested\./)).toBeInTheDocument()
    expect(posted.map((p) => p.kind)).toEqual(['confirm'])
  })
})

describe('Dismiss', () => {
  it('dismisses the card, then shows what the next read says', async () => {
    const dismissed = proposalOut({ status: 'canceled', canceledReason: 'dismissed' })
    const { api, user } = open(withTurn(bookingTurn(proposalOut())))
    const posted = onProposalAction(() => {
      api.setCurrent(withTurn(bookingTurn(dismissed)))
      return HttpResponse.json(dismissed)
    })
    await card()

    await user.click(screen.getByRole('button', { name: /^Dismiss/ }))

    expect(await screen.findByText('You dismissed this. Nothing was changed.')).toBeInTheDocument()
    expect(posted).toHaveLength(1)
    expect(posted[0]).toMatchObject({ kind: 'cancel' })
  })
})

describe('Ask again', () => {
  it('puts the turn’s question in the composer and focuses it, without sending', async () => {
    const { user } = open(
      withTurn(bookingTurn(proposalOut({ status: 'expired' }), { question: QUESTION })),
    )
    const posted = onTurn(() => new HttpResponse(null, { status: 500 }))
    await card()

    await user.click(screen.getByRole('button', { name: 'Ask again' }))

    await waitFor(() => expect(composer()).toHaveValue(QUESTION))
    expect(composer()).toHaveFocus()
    expect(posted).toHaveLength(0)
  })

  it('focuses the composer even when focus was not in the card', async () => {
    open(withTurn(bookingTurn(proposalOut({ status: 'expired' }))))
    await card()
    const ask = screen.getByRole('button', { name: 'Ask again' })

    act(() => ask.click())

    await waitFor(() => expect(composer()).toHaveFocus())
  })
})
