import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { DAY_METRICS, DAY_TURNS } from '@/app/gallery/fixtures/console'
import {
  getEndSessionMutationKey,
  getGetAssistantTextsQueryKey,
  getGetCurrentConversationQueryKey,
} from '@/api/generated'
import { useChatStore } from '@/features/chat/store'
import { installFakeApi } from '@/test/fake-api'
import {
  conversationOut,
  eventStream,
  installAssistantApi,
  onTurn,
  openStream,
  problemResponse,
  proposalOut,
  TEXTS,
  turnOut,
} from '@/test/fake-assistant'
import { installFakeConsole } from '@/test/fake-console'
import { server } from '@/test/msw'
import { personaSwitcher } from '@/test/persona-menu'
import { renderApp } from '@/test/render-app'
import { DUMMY_TURNSTILE_TOKEN } from '@/test/turnstile'
import { useTourStore } from './store'

// The guided tour's runner (screen 15) inside the real shell, against the fake API.

const SWITCH = () => `${window.location.origin}/api/v1/session/persona`
const TURN = 'c0ffee00-0000-4000-8000-0000000000aa'
const LEFT = 'Tour closed. You can pick it up again from the persona menu.'

type Persona = 'priya' | 'mateo' | 'marcus' | 'dana'

/** The tour at a step as `persona`, already arrived (no switch to wait for). */
function setup(
  persona: Persona,
  step: number,
  over: Partial<ReturnType<typeof useTourStore.getState>> = {},
  /** Installs routes that win over the fake's, before the page loads. */
  before: () => void = () => {},
  at = '/ask',
) {
  installFakeApi(persona)
  const api = installAssistantApi()
  before()
  useTourStore.setState({
    started: true,
    active: true,
    step,
    sent: [],
    turnId: null,
    lost: false,
    outcome: null,
    entering: false,
    ...over,
  })
  return { api, ...renderApp({ at }) }
}

const mark = (title: RegExp | string) => screen.findByRole('dialog', { name: title })
const toast = () => document.querySelector<HTMLElement>('[data-slot="toast"]')

function completes(question: string, extra: [string, unknown][] = []) {
  return [
    ['turn.started', { turnId: TURN }],
    ...extra,
    ['text.delta', { text: `Answer to ${question}` }],
    [
      'turn.completed',
      { turnId: TURN, servedBy: 'scripted', usage: { inputTokens: 1, outputTokens: 1 } },
    ],
  ] as [string, unknown][]
}

beforeEach(() => {
  useChatStore.setState(useChatStore.getInitialState())
})

describe('the coach mark', () => {
  it('shows step 1 for Priya on her home, with no Back, her chip, and Skip', async () => {
    setup('priya', 0)
    const card = await mark(/Ask a policy question/)
    expect(within(card).getByText('Step 1 of 10')).toBeInTheDocument()
    expect(within(card).queryByRole('button', { name: 'Back' })).not.toBeInTheDocument()
    expect(
      within(card).getByRole('button', { name: /^How many sick days do I get\?/ }),
    ).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Skip this step' })).toBeInTheDocument()
    expect(card.querySelector('h2')).toHaveFocus()
  })

  it('sends a chip as typed through the conversation, shows Sent, and offers Next when the turn ends', async () => {
    const stream = openStream()
    const posted = onTurn(() => stream.response())
    const { user, api } = setup('priya', 0)
    const card = await mark(/Ask a policy question/)
    // The composer is on the page before the texts load; the chip waits for them.
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    await user.click(within(card).getByRole('button', { name: /^How many sick days/ }))
    await waitFor(() => expect(posted).toHaveLength(1))
    expect(posted[0]!.question).toBe('How many sick days do I get?')
    const chip = await within(card).findByRole('button', { name: /sent$/ })
    expect(chip).toHaveAttribute('aria-disabled', 'true')
    expect(within(card).getByText('Sent')).toBeInTheDocument()

    // While the answer streams: still Skip.
    stream.push('turn.started', { turnId: TURN })
    stream.push('text.delta', { text: 'Answer' })
    await waitFor(() => expect(useChatStore.getState().status).toBe('streaming'))
    expect(screen.getByRole('button', { name: 'Skip this step' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Next' })).not.toBeInTheDocument()

    api.setCurrent(
      conversationOut({ turns: [turnOut({ id: TURN, question: 'How many sick days do I get?' })] }),
    )
    stream.push('turn.completed', {
      turnId: TURN,
      servedBy: 'scripted',
      usage: { inputTokens: 1, outputTokens: 1 },
    })
    stream.close()
    expect(await screen.findByRole('button', { name: 'Next' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Skip this step' })).not.toBeInTheDocument()
  })

  it('holds a chip pressed before the assistant’s texts load, then sends it once', async () => {
    const posted = onTurn((question) => eventStream(...completes(question)))
    let release = () => {}
    const held = new Promise<void>((resolve) => (release = resolve))
    const { user } = setup('priya', 0, {}, () =>
      server.use(
        http.get(`${window.location.origin}/api/v1/assistant/texts`, async () => {
          await held
          return HttpResponse.json(TEXTS)
        }),
      ),
    )
    const card = await mark(/Ask a policy question/)
    await user.click(within(card).getByRole('button', { name: /^How many sick days/ }))
    expect(posted).toEqual([])
    release()
    await waitFor(() => expect(posted).toHaveLength(1))
    expect(within(card).getByRole('button', { name: /sent$/ })).toBeInTheDocument()
  })

  it('drops a chip held for the texts when the visitor moves to another step', async () => {
    const posted = onTurn((question) => eventStream(...completes(question)))
    let release = () => {}
    const held = new Promise<void>((resolve) => (release = resolve))
    const { user } = setup('marcus', 3, {}, () =>
      server.use(
        http.get(`${window.location.origin}/api/v1/assistant/texts`, async () => {
          await held
          return HttpResponse.json(TEXTS)
        }),
      ),
    )
    const card = await mark(/Decide as the manager/)
    await user.click(within(card).getByRole('button', { name: /^Anything waiting on me\?/ }))
    await user.click(screen.getByRole('button', { name: 'Skip this step' }))
    await mark(/Ask about someone’s absence/)
    release()
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    await new Promise((resolve) => setTimeout(resolve, 300))
    expect(posted).toEqual([])
    expect(useTourStore.getState().sent).toEqual([])
  })

  it('holds a second chip pressed while the first one’s answer streams, and sends it when the answer is done', async () => {
    const stream = openStream()
    const posted = onTurn((question) =>
      question === 'Anything waiting on me?'
        ? stream.response()
        : eventStream(...completes(question)),
    )
    const { user } = setup('marcus', 3)
    const card = await mark(/Decide as the manager/)
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    await user.click(within(card).getByRole('button', { name: /^Anything waiting on me\?/ }))
    await waitFor(() => expect(posted).toHaveLength(1))
    stream.push('turn.started', { turnId: TURN })
    stream.push('text.delta', { text: 'Answer' })
    await waitFor(() => expect(useChatStore.getState().status).toBe('streaming'))
    await user.click(within(card).getByRole('button', { name: /^Approve Priya/ }))
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(posted).toHaveLength(1)
    stream.push('turn.completed', {
      turnId: TURN,
      servedBy: 'scripted',
      usage: { inputTokens: 1, outputTokens: 1 },
    })
    stream.close()
    await waitFor(() => expect(posted).toHaveLength(2))
    expect(posted[1]!.question).toBe('Approve Priya’s request.')
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(posted).toHaveLength(2)
  })

  it('keeps every chip pressed while the conversation is busy, and sends them in order, once each', async () => {
    const first = openStream()
    const posted = onTurn((question) =>
      question === 'Anything waiting on me?'
        ? first.response()
        : eventStream(...completes(question)),
    )
    let release = () => {}
    const held = new Promise<void>((resolve) => (release = resolve))
    const { user } = setup('marcus', 3, {}, () =>
      server.use(
        http.get(`${window.location.origin}/api/v1/assistant/texts`, async () => {
          await held
          return HttpResponse.json(TEXTS)
        }),
      ),
    )
    const card = await mark(/Decide as the manager/)
    await user.click(within(card).getByRole('button', { name: /^Anything waiting on me\?/ }))
    await user.click(within(card).getByRole('button', { name: /^Approve Priya/ }))
    expect(posted).toEqual([])
    release()
    await waitFor(() => expect(posted).toHaveLength(1))
    expect(posted[0]!.question).toBe('Anything waiting on me?')
    first.push('turn.started', { turnId: TURN })
    await waitFor(() => expect(useChatStore.getState().status).toBe('streaming'))
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(posted).toHaveLength(1)
    first.push('turn.completed', {
      turnId: TURN,
      servedBy: 'scripted',
      usage: { inputTokens: 1, outputTokens: 1 },
    })
    first.close()
    await waitFor(() => expect(posted).toHaveLength(2))
    expect(posted[1]!.question).toBe('Approve Priya’s request.')
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(posted).toHaveLength(2)
  })

  it('sends two chips pressed in the same tick, in order', async () => {
    const posted = onTurn((question) => eventStream(...completes(question)))
    setup('marcus', 3)
    const card = await mark(/Decide as the manager/)
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    await new Promise((resolve) => setTimeout(resolve, 100))
    const first = within(card).getByRole('button', { name: /^Anything waiting on me\?/ })
    const second = within(card).getByRole('button', { name: /^Approve Priya/ })
    act(() => {
      fireEvent.click(first)
      fireEvent.click(second)
    })
    await waitFor(() => expect(posted).toHaveLength(2))
    expect(posted.map((p) => p.question)).toEqual([
      'Anything waiting on me?',
      'Approve Priya’s request.',
    ])
    expect(useTourStore.getState().sent).toEqual([0, 1])
  })

  it('never sends a chip twice: it stays sent when the send ends without a turn, since the server may hold the question', async () => {
    // The server accepts the send (200) and closes the stream with no event. The send is taken
    // but leaves no turn to follow: the chip is not given back, and the step finishes without a
    // result (the visitor can still type the question).
    const posted = onTurn(() => eventStream())
    const { user } = setup('priya', 0)
    const card = await mark(/Ask a policy question/)
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    await user.click(within(card).getByRole('button', { name: /^How many sick days/ }))
    await waitFor(() => expect(posted).toHaveLength(1))
    await waitFor(() => expect(useChatStore.getState().sendError).not.toBeNull())
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(useTourStore.getState()).toMatchObject({ sent: [0], turnId: null, lost: true })
    expect(await within(card).findByRole('button', { name: 'Next' })).toBeInTheDocument()
    await user.click(within(card).getByRole('button', { name: /sent$/ }))
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(posted).toHaveLength(1)
  })

  it('gives the chip back when its send returned without starting anything', async () => {
    // A typed send takes the composer in the same frame: the chip's send returns early with no
    // error. The server never saw the question, so the chip can be pressed again.
    const posted = onTurn(() => eventStream(...completes('x')))
    const { user } = setup('priya', 0)
    const card = await mark(/Ask a policy question/)
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    const original = useTourStore.getState().markSent
    useTourStore.setState({
      markSent: (chip) => {
        original(chip)
        useChatStore.setState({ waitingToSend: true })
      },
    })
    try {
      await user.click(within(card).getByRole('button', { name: /^How many sick days/ }))
      await waitFor(() => expect(useTourStore.getState().sent).toEqual([]))
    } finally {
      useTourStore.setState({ markSent: original })
      useChatStore.setState({ waitingToSend: false })
    }
    expect(posted).toHaveLength(0)
    expect(within(card).queryByText('Sent')).not.toBeInTheDocument()
    await user.click(within(card).getByRole('button', { name: /^How many sick days/ }))
    await waitFor(() => expect(posted).toHaveLength(1))
  })

  it('leaves the visitor’s own error alone when the chip’s send returns without starting', async () => {
    const posted = onTurn(() => eventStream(...completes('x')))
    const { user } = setup('priya', 0)
    const card = await mark(/Ask a policy question/)
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    const original = useTourStore.getState().markSent
    useTourStore.setState({
      markSent: (chip) => {
        original(chip)
        useChatStore.setState({ waitingToSend: true })
      },
    })
    useChatStore.setState({ sendError: 'Typed question failed.' })
    try {
      await user.click(within(card).getByRole('button', { name: /^How many sick days/ }))
      await waitFor(() => expect(useTourStore.getState().sent).toEqual([]))
    } finally {
      useTourStore.setState({ markSent: original })
      useChatStore.setState({ waitingToSend: false })
    }
    expect(useChatStore.getState().sendError).toBe('Typed question failed.')
    expect(posted).toHaveLength(0)
    useChatStore.setState({ sendError: null })
  })

  it('gives the chip back when the chat store turns the send away as still answering', async () => {
    // The refusal sets the store's "still answering" error and returns false: nothing reached the
    // server, so the error showing must not keep the chip Sent.
    const posted = onTurn(() => eventStream(...completes('x')))
    const { user } = setup('priya', 0)
    const card = await mark(/Ask a policy question/)
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    const original = useTourStore.getState().markSent
    useTourStore.setState({
      markSent: (chip) => {
        original(chip)
        useChatStore.setState({ status: 'streaming' })
      },
    })
    try {
      await user.click(within(card).getByRole('button', { name: /^How many sick days/ }))
      await waitFor(() => expect(useChatStore.getState().sendError).not.toBeNull())
      await waitFor(() => expect(useTourStore.getState().sent).toEqual([]))
    } finally {
      useTourStore.setState({ markSent: original })
      useChatStore.setState({ status: 'idle', sendError: null })
    }
    expect(posted).toHaveLength(0)
    expect(within(card).queryByText('Sent')).not.toBeInTheDocument()
  })

  it('does not count an earlier turn with the chip’s words as the answer to this press', async () => {
    const stream = openStream()
    const posted = onTurn(() => stream.response())
    const { user } = setup('priya', 2, {}, () =>
      installAssistantApi({
        conversation: conversationOut({
          turns: [
            turnOut({
              id: 'c0ffee00-0000-4000-8000-0000000000bb',
              question: 'Book next Friday off.',
            }),
          ],
        }),
      }),
    )
    const card = await mark(/Book a day off/)
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    await user.click(within(card).getByRole('button', { name: /^Book next Friday off\./ }))
    await waitFor(() => expect(posted).toHaveLength(1))
    // The new answer is still streaming: the earlier turn must not finish the step or flash the
    // line.
    await new Promise((resolve) => setTimeout(resolve, 450))
    expect(within(card).queryByRole('status')).not.toBeInTheDocument()
    expect(within(card).queryByRole('button', { name: 'Next' })).not.toBeInTheDocument()
    stream.close()
  })

  describe('after a reload mid-step', () => {
    const OLD = 'c0ffee00-0000-4000-8000-0000000000bb'
    const reloaded = async (turns: ReturnType<typeof turnOut>[]) => {
      installFakeApi('priya')
      installAssistantApi({ conversation: conversationOut({ turns }) })
      sessionStorage.setItem(
        'od.tour',
        JSON.stringify({
          state: {
            started: true,
            active: true,
            step: 2,
            sent: [0],
            turnId: TURN,
            lost: false,
            outcome: null,
            entering: false,
          },
          version: 3,
        }),
      )
      await useTourStore.persist.rehydrate()
      renderApp({ at: '/ask' })
      return mark(/Book a day off/)
    }

    it('finds the chip’s own turn and its card: Next, no missing line', async () => {
      const card = await reloaded([
        turnOut({
          id: OLD,
          question: 'Book Monday off.',
          proposals: [proposalOut({ turnRunning: false })],
        }),
        turnOut({
          id: TURN,
          question: 'Book next Friday off.',
          proposals: [
            proposalOut({ id: 'c0ffee00-0000-4000-8000-0000000000b2', turnRunning: false }),
          ],
        }),
      ])
      expect(await within(card).findByRole('button', { name: 'Next' })).toBeInTheDocument()
      await new Promise((resolve) => setTimeout(resolve, 400))
      expect(within(card).queryByRole('status')).not.toBeInTheDocument()
      expect(useTourStore.getState().turnId).toBe(TURN)
    })

    it('does not take an earlier turn’s card for the result of a turn that has none', async () => {
      const card = await reloaded([
        turnOut({
          id: OLD,
          question: 'Book Monday off.',
          proposals: [proposalOut({ turnRunning: false })],
        }),
        turnOut({ id: TURN, question: 'Book next Friday off.' }),
      ])
      expect(await within(card).findByRole('status')).toHaveTextContent(
        /^The assistant usually shows a confirm card here/,
      )
    })

    it('waits while the chip’s turn is still running', async () => {
      const card = await reloaded([
        turnOut({
          id: OLD,
          question: 'Book Monday off.',
          proposals: [proposalOut({ turnRunning: false })],
        }),
        turnOut({ id: TURN, question: 'Book next Friday off.', status: 'running' }),
      ])
      await waitFor(() =>
        expect(document.querySelector('[data-slot="confirm-card"]')).not.toBeNull(),
      )
      await new Promise((resolve) => setTimeout(resolve, 450))
      expect(within(card).queryByRole('status')).not.toBeInTheDocument()
      expect(within(card).queryByRole('button', { name: 'Next' })).not.toBeInTheDocument()
    })
  })

  it('a chip pressed twice sends once', async () => {
    const stream = openStream()
    const posted = onTurn(() => stream.response())
    const { user } = setup('priya', 0)
    const card = await mark(/Ask a policy question/)
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    const chip = within(card).getByRole('button', { name: /^How many sick days/ })
    await user.click(chip)
    await user.click(chip)
    await waitFor(() => expect(posted).toHaveLength(1))
    stream.close()
  })

  it('a step with no chips shows Next from the start', async () => {
    setup('dana', 8)
    expect(await screen.findByRole('button', { name: 'Next' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Skip this step' })).not.toBeInTheDocument()
  })

  it('shows the missing line and Next when the turn ends without the expected card', async () => {
    const posted = onTurn((question) => eventStream(...completes(question)))
    const { user, api } = setup('priya', 2)
    const card = await mark(/Book a day off/)
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    expect(within(card).queryByRole('status')).not.toBeInTheDocument()
    api.setCurrent(
      conversationOut({ turns: [turnOut({ id: TURN, question: 'Book next Friday off.' })] }),
    )
    await user.click(within(card).getByRole('button', { name: /^Book next Friday off\./ }))
    await waitFor(() => expect(posted).toHaveLength(1))
    expect(await within(card).findByRole('status')).toHaveTextContent(
      /^The assistant usually shows a confirm card here/,
    )
    expect(within(card).getByRole('button', { name: 'Next' })).toBeInTheDocument()
  })

  it('does not count a card already on the page as the step’s result', async () => {
    const posted = onTurn((question) => eventStream(...completes(question)))
    const { user } = setup('priya', 2, {}, () => {})
    const older = conversationOut({
      turns: [
        turnOut({
          id: 'c0ffee00-0000-4000-8000-0000000000bb',
          question: 'Book Monday off.',
          proposals: [proposalOut({ turnRunning: false })],
        }),
      ],
    })
    // The saved conversation already holds a confirm card when the step is entered.
    installAssistantApi({ conversation: older })
    const card = await mark(/Book a day off/)
    await waitFor(() => expect(document.querySelector('[data-slot="confirm-card"]')).not.toBeNull())
    // Give the coach mark's read of the page (one animation frame) time to see the card.
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(within(card).queryByRole('button', { name: 'Next' })).not.toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Skip this step' })).toBeInTheDocument()
    // A turn that brings no new card still ends in the missing line.
    await user.click(within(card).getByRole('button', { name: /^Book next Friday off\./ }))
    await waitFor(() => expect(posted).toHaveLength(1))
    expect(await within(card).findByRole('status')).toHaveTextContent(
      /^The assistant usually shows a confirm card here/,
    )
  })

  it('shows Next without the missing line when the card appears', async () => {
    onTurn((question) =>
      eventStream(...completes(question, [['proposal', proposalOut({ turnRunning: true })]])),
    )
    const { user, api } = setup('priya', 2)
    const card = await mark(/Book a day off/)
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    api.setCurrent(
      conversationOut({
        turns: [
          turnOut({
            id: TURN,
            question: 'Book next Friday off.',
            proposals: [proposalOut({ turnRunning: false })],
          }),
        ],
      }),
    )
    await user.click(within(card).getByRole('button', { name: /^Book next Friday off\./ }))
    expect(await within(card).findByRole('button', { name: 'Next' })).toBeInTheDocument()
    expect(document.querySelector('[data-slot="confirm-card"]')).not.toBeNull()
    // Wait past the missing line's settle time: it never comes.
    await new Promise((resolve) => setTimeout(resolve, 400))
    expect(within(card).queryByRole('status')).not.toBeInTheDocument()
  })

  it('shows the result when an older card unmounts as the chip’s own card appears', async () => {
    const OLD = 'c0ffee00-0000-4000-8000-0000000000bb'
    const stream = openStream()
    onTurn(() => stream.response())
    const { user, api } = setup('priya', 2, {}, () =>
      installAssistantApi({
        conversation: conversationOut({
          turns: [
            turnOut({
              id: OLD,
              question: 'Book Monday off.',
              proposals: [proposalOut({ turnRunning: false })],
            }),
          ],
        }),
      }),
    )
    const card = await mark(/Book a day off/)
    await waitFor(() => expect(document.querySelector('[data-slot="confirm-card"]')).not.toBeNull())
    await user.click(within(card).getByRole('button', { name: /^Book next Friday off\./ }))
    stream.push('turn.started', { turnId: TURN })
    stream.push(
      'proposal',
      proposalOut({ id: 'c0ffee00-0000-4000-8000-0000000000b2', turnRunning: true }),
    )
    stream.push('text.delta', { text: 'Answer' })
    await waitFor(() => expect(useTourStore.getState().turnId).toBe(TURN))
    // The saved copy takes over: the older turn is gone from it, so the card count stays at one.
    api.setCurrent(
      conversationOut({
        turns: [
          turnOut({
            id: TURN,
            question: 'Book next Friday off.',
            proposals: [
              proposalOut({ id: 'c0ffee00-0000-4000-8000-0000000000b2', turnRunning: false }),
            ],
          }),
        ],
      }),
    )
    stream.push('turn.completed', {
      turnId: TURN,
      servedBy: 'scripted',
      usage: { inputTokens: 1, outputTokens: 1 },
    })
    stream.close()
    expect(await within(card).findByRole('button', { name: 'Next' })).toBeInTheDocument()
    await new Promise((resolve) => setTimeout(resolve, 450))
    expect(within(card).queryByRole('status')).not.toBeInTheDocument()
  })

  it('stores the chip’s turn ID as soon as the server gives it, before the answer ends', async () => {
    const stream = openStream()
    onTurn(() => stream.response())
    const { user } = setup('priya', 0)
    const card = await mark(/Ask a policy question/)
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    await user.click(within(card).getByRole('button', { name: /^How many sick days/ }))
    expect(useTourStore.getState().turnId).toBeNull()
    stream.push('turn.started', { turnId: TURN })
    await waitFor(() => expect(useTourStore.getState().turnId).toBe(TURN))
    expect(within(card).queryByRole('button', { name: 'Next' })).not.toBeInTheDocument()
    stream.close()
  })

  it('moves on with Skip and Next, and back with Back, switching persona each time', async () => {
    const { user } = setup('priya', 0)
    await mark(/Ask a policy question/)
    await user.click(screen.getByRole('button', { name: 'Skip this step' }))
    await mark(/Same question, another state/)
    expect(personaSwitcher()).toHaveAccessibleName(/^Mateo Alvarez/)
    expect(useTourStore.getState().step).toBe(1)
    await user.click(screen.getByRole('button', { name: 'Back' }))
    await mark(/Ask a policy question/)
    expect(personaSwitcher()).toHaveAccessibleName(/^Priya Raman/)
    expect(useTourStore.getState().step).toBe(0)
  })
})

describe('a latched outcome', () => {
  it('keeps Next and shows no missing line when the visitor leaves the page after the card appeared', async () => {
    onTurn((question) =>
      eventStream(...completes(question, [['proposal', proposalOut({ turnRunning: true })]])),
    )
    const { user, api, router } = setup('priya', 2)
    const card = await mark(/Book a day off/)
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    api.setCurrent(
      conversationOut({
        turns: [
          turnOut({
            id: TURN,
            question: 'Book next Friday off.',
            proposals: [proposalOut({ turnRunning: false })],
          }),
        ],
      }),
    )
    await user.click(within(card).getByRole('button', { name: /^Book next Friday off\./ }))
    expect(await within(card).findByRole('button', { name: 'Next' })).toBeInTheDocument()
    await act(() => router.navigate('/handbook'))
    await new Promise((resolve) => setTimeout(resolve, 450))
    expect(within(card).queryByRole('status')).not.toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Next' })).toBeInTheDocument()
    expect(useTourStore.getState().outcome).toBe('result')
  })

  it('keeps Next after a new conversation takes the finished turn away', async () => {
    onTurn((question) => eventStream(...completes(question)))
    const { user, api, queryClient } = setup('priya', 0)
    const card = await mark(/Ask a policy question/)
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    api.setCurrent(
      conversationOut({ turns: [turnOut({ id: TURN, question: 'How many sick days do I get?' })] }),
    )
    await user.click(within(card).getByRole('button', { name: /^How many sick days/ }))
    expect(await within(card).findByRole('button', { name: 'Next' })).toBeInTheDocument()
    // "Start a new conversation": the turn leaves the chat store and the current conversation.
    api.setCurrent(conversationOut({ turns: [] }))
    act(() => useChatStore.setState(useChatStore.getInitialState()))
    await act(() => queryClient.invalidateQueries())
    await new Promise((resolve) => setTimeout(resolve, 450))
    expect(within(card).getByRole('button', { name: 'Next' })).toBeInTheDocument()
  })

  it('clears the missing line when the chip’s card shows up later', async () => {
    onTurn((question) => eventStream(...completes(question)))
    const { user, api, queryClient } = setup('priya', 2)
    const card = await mark(/Book a day off/)
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    api.setCurrent(
      conversationOut({ turns: [turnOut({ id: TURN, question: 'Book next Friday off.' })] }),
    )
    await user.click(within(card).getByRole('button', { name: /^Book next Friday off\./ }))
    expect(await within(card).findByRole('status')).toBeInTheDocument()
    api.setCurrent(
      conversationOut({
        turns: [
          turnOut({
            id: TURN,
            question: 'Book next Friday off.',
            proposals: [proposalOut({ turnRunning: false })],
          }),
        ],
      }),
    )
    await act(() => queryClient.invalidateQueries())
    await waitFor(() => expect(within(card).queryByRole('status')).not.toBeInTheDocument())
    expect(useTourStore.getState().outcome).toBe('result')
    expect(within(card).getByRole('button', { name: 'Next' })).toBeInTheDocument()
  })
})

describe('a chip pressed off the step’s page', () => {
  it('goes back to the step’s page first, then sends once', async () => {
    const posted = onTurn((question) => eventStream(...completes(question)))
    const { user, router } = setup('priya', 0, {}, () => {}, '/handbook')
    const card = await mark(/Ask a policy question/)
    expect(router.state.location.pathname).toBe('/handbook')
    await user.click(within(card).getByRole('button', { name: /^How many sick days/ }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/ask'))
    await waitFor(() => expect(posted).toHaveLength(1))
    expect(await screen.findByText('Answer to How many sick days do I get?')).toBeInTheDocument()
    expect(useTourStore.getState().sent).toEqual([0])
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(posted).toHaveLength(1)
  })
})

describe('a chip that cannot be sent', () => {
  it('drops a chip held for texts that failed to load, and leaves it pressable', async () => {
    const posted = onTurn((question) => eventStream(...completes(question)))
    let release = () => {}
    const held = new Promise<void>((resolve) => (release = resolve))
    let failing = true
    const { user, queryClient } = setup('priya', 0, {}, () =>
      server.use(
        http.get(`${window.location.origin}/api/v1/assistant/texts`, async () => {
          if (!failing) return HttpResponse.json(TEXTS)
          await held
          return HttpResponse.json(
            { type: 'about:blank', title: 'Down', status: 500, instance: '/' },
            { status: 500 },
          )
        }),
      ),
    )
    const card = await mark(/Ask a policy question/)
    await user.click(within(card).getByRole('button', { name: /^How many sick days/ }))
    release()
    await waitFor(() =>
      expect(queryClient.getQueryState(getGetAssistantTextsQueryKey())?.status).toBe('error'),
    )
    expect(useTourStore.getState().sent).toEqual([])
    // The texts come back later: the dropped chip must not fire by itself.
    failing = false
    await queryClient.refetchQueries({ queryKey: getGetAssistantTextsQueryKey() })
    await new Promise((resolve) => setTimeout(resolve, 150))
    expect(posted).toEqual([])
    expect(useTourStore.getState().sent).toEqual([])
    await user.click(within(card).getByRole('button', { name: /^How many sick days/ }))
    await waitFor(() => expect(posted).toHaveLength(1))
  })

  it('gives the chip back when the server fails before taking the question', async () => {
    const posted = onTurn((question) => eventStream(...completes(question)))
    const { user } = setup('priya', 2, {}, () =>
      server.use(
        http.post(`${window.location.origin}/api/v1/assistant/conversations`, () =>
          HttpResponse.json(
            { type: 'about:blank', title: 'Down', status: 500, instance: '/' },
            { status: 500 },
          ),
        ),
      ),
    )
    const card = await mark(/Book a day off/)
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    await user.click(within(card).getByRole('button', { name: /^Book next Friday off\./ }))
    await waitFor(() => expect(useChatStore.getState().sendError).not.toBeNull())
    await waitFor(() => expect(useTourStore.getState().sent).toEqual([]))
    expect(posted).toEqual([])
    expect(within(card).queryByRole('status')).not.toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Skip this step' })).toBeInTheDocument()
  })

  it.each([
    ['409 turn-running', () => problemResponse(409, 'turn-running', 'Still answering.')],
    ['422 personal-data', () => problemResponse(422, 'personal-data', 'Personal data.')],
  ])(
    'gives the chip back after a %s refusal, pressable again and not stuck',
    async (_name, refuse) => {
      const posted = onTurn(refuse)
      const { user } = setup('priya', 0)
      const card = await mark(/Ask a policy question/)
      await screen.findByRole('textbox', { name: 'Ask Open Door' })
      await user.click(within(card).getByRole('button', { name: /^How many sick days/ }))
      await waitFor(() => expect(posted).toHaveLength(1))
      await waitFor(() => expect(useTourStore.getState().sent).toEqual([]))
      expect(within(card).queryByText('Sent')).not.toBeInTheDocument()
      expect(within(card).queryByRole('button', { name: 'Next' })).not.toBeInTheDocument()
      await user.click(within(card).getByRole('button', { name: /^How many sick days/ }))
      await waitFor(() => expect(posted).toHaveLength(2))
    },
  )

  it('keeps the chip Sent after a proxy 504, since the API may have started the turn', async () => {
    const posted = onTurn(() => new HttpResponse('<html>Gateway timeout</html>', { status: 504 }))
    const { user } = setup('priya', 0)
    const card = await mark(/Ask a policy question/)
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    await user.click(within(card).getByRole('button', { name: /^How many sick days/ }))
    await waitFor(() => expect(posted).toHaveLength(1))
    await waitFor(() => expect(useChatStore.getState().sendError).not.toBeNull())
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(useTourStore.getState().sent).toEqual([0])
    expect(within(card).getByRole('button', { name: /sent$/ })).toHaveAttribute(
      'aria-disabled',
      'true',
    )
  })

  it.each([
    ['the assistant texts', '/api/v1/assistant/texts', getGetAssistantTextsQueryKey()],
    [
      'the conversation',
      '/api/v1/assistant/conversations/current',
      getGetCurrentConversationQueryKey(),
    ],
  ])(
    'still sends a chip when a background read of %s fails while the cached copy shows',
    async (_name, path, queryKey) => {
      const posted = onTurn((question) => eventStream(...completes(question)))
      let failing = false
      const { user, queryClient } = setup('priya', 0, {}, () =>
        server.use(
          // Returning nothing falls through to the fake's own handler.
          http.get(`${window.location.origin}${path}`, () => {
            if (!failing) return undefined
            return HttpResponse.json(
              { type: 'about:blank', title: 'Down', status: 500, instance: '/' },
              { status: 500 },
            )
          }),
        ),
      )
      const card = await mark(/Ask a policy question/)
      await screen.findByRole('textbox', { name: 'Ask Open Door' })
      await waitFor(() => expect(queryClient.getQueryState(queryKey)?.status).toBe('success'))
      failing = true
      await act(() => queryClient.refetchQueries({ queryKey }).catch(() => {}))
      await waitFor(() => expect(queryClient.getQueryState(queryKey)?.status).toBe('error'))
      expect(queryClient.getQueryData(queryKey)).toBeDefined()
      await user.click(within(card).getByRole('button', { name: /^How many sick days/ }))
      await waitFor(() => expect(posted).toHaveLength(1))
    },
  )

  it('does not touch the next step’s chips when a refused send reports after the step changed', async () => {
    let release = () => {}
    const held = new Promise<void>((resolve) => (release = resolve))
    const posted = onTurn((question) => eventStream(...completes(question)))
    const { user } = setup('priya', 2, {}, () =>
      server.use(
        http.post(`${window.location.origin}/api/v1/assistant/conversations`, async () => {
          await held
          return HttpResponse.json(
            { type: 'about:blank', title: 'Down', status: 500, instance: '/' },
            { status: 500 },
          )
        }),
      ),
    )
    const card = await mark(/Book a day off/)
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    await user.click(within(card).getByRole('button', { name: /^Book next Friday off\./ }))
    await waitFor(() => expect(useTourStore.getState().sent).toEqual([0]))
    await user.click(screen.getByRole('button', { name: 'Skip this step' }))
    await mark(/Decide as the manager/)
    // The visitor presses the next step's first chip (the same index) before the old send reports.
    act(() => useTourStore.getState().markSent(0))
    release()
    await new Promise((resolve) => setTimeout(resolve, 200))
    expect(useTourStore.getState().sent).toEqual([0])
    expect(posted).toEqual([])
  })
})

describe('beginning the tour', () => {
  it('goes through the entering check: step 1 shows on /ask as Priya, with no persona switch', async () => {
    let switches = 0
    server.use(
      http.post(SWITCH(), () => {
        switches++
        return HttpResponse.json({}, { status: 500 })
      }),
    )
    setup('priya', 0, { entering: false })
    useTourStore.getState().begin()
    await mark(/Ask a policy question/)
    expect(useTourStore.getState().entering).toBe(false)
    expect(switches).toBe(0)
  })
})

describe('a typed question that fails while the chip is pending', () => {
  it('does not end the chip’s step: no missing line', async () => {
    const stream = openStream()
    const posted = onTurn(() => stream.response())
    const { user } = setup('priya', 2)
    const card = await mark(/Book a day off/)
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    await user.click(within(card).getByRole('button', { name: /^Book next Friday off\./ }))
    await waitFor(() => expect(posted).toHaveLength(1))
    // A typed question fails now, in the chat store's global error, while the chip's own turn is
    // still coming.
    act(() => useChatStore.setState({ status: 'idle', sendError: 'Typed question failed.' }))
    await new Promise((resolve) => setTimeout(resolve, 450))
    expect(within(card).queryByRole('status')).not.toBeInTheDocument()
    expect(within(card).queryByRole('button', { name: 'Next' })).not.toBeInTheDocument()
    stream.close()
  })
})

describe('switching persona for a step', () => {
  it('shows the switcher busy and the toast, and the coach mark only after the switch', async () => {
    const fake = installFakeApi('priya')
    installAssistantApi()
    let release = () => {}
    const held = new Promise<void>((resolve) => (release = resolve))
    const passthrough = http.put(SWITCH(), async ({ request }) => {
      await held
      const { persona } = (await request.json()) as { persona: Persona }
      fake.signIn(persona)
      return HttpResponse.json((await import('@/test/fixtures')).meFor(persona as Persona))
    })
    server.use(passthrough)
    useTourStore.setState({ started: true, active: true, step: 1, sent: [], entering: true })
    renderApp({ at: '/ask' })

    expect(await screen.findByRole('button', { name: /^Switching to Mateo…/ })).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: /Same question/ })).not.toBeInTheDocument()
    release()
    const card = await mark(/Same question, another state/)
    expect(within(card).getByText(/^Now you’re Mateo Alvarez/)).toBeInTheDocument()
    await waitFor(() => expect(toast()).toHaveTextContent('Now viewing as Mateo Alvarez.'))
    expect(useTourStore.getState()).toMatchObject({ active: true, step: 1, entering: false })
  })

  it('takes Dana to the console for step 9 and points at the flagged row', async () => {
    installFakeApi('priya')
    installAssistantApi()
    installFakeConsole({
      metrics: DAY_METRICS,
      pages: { '': { items: DAY_TURNS, nextCursor: null } },
    })
    useTourStore.setState({ started: true, active: true, step: 8, sent: [], entering: true })
    const { router } = renderApp({ at: '/ask' })
    const card = await mark(/See what the AI did/)
    expect(router.state.location.pathname).toBe('/console')
    expect(within(card).getByRole('button', { name: 'Next' })).toBeInTheDocument()
    await waitFor(() => expect(document.querySelector('[data-slot="tour-ring"]')).not.toBeNull())
  })

  it('reads no conversation or assistant texts on a step with no chips', async () => {
    installFakeApi('dana')
    installAssistantApi()
    const reads: string[] = []
    server.events.on('request:start', ({ request }) => {
      const path = new URL(request.url).pathname
      if (path.endsWith('/assistant/texts') || path.endsWith('/conversations/current')) {
        reads.push(path)
      }
    })
    installFakeConsole({
      metrics: DAY_METRICS,
      pages: { '': { items: DAY_TURNS, nextCursor: null } },
    })
    useTourStore.setState({ started: true, active: true, step: 8, sent: [], entering: true })
    renderApp({ at: '/console' })
    const card = await mark(/See what the AI did/)
    expect(within(card).getByRole('button', { name: 'Next' })).toBeInTheDocument()
    await new Promise((resolve) => setTimeout(resolve, 100))
    server.events.removeAllListeners()
    expect(reads).toEqual([])
  })

  it('tries a failed switch once, leaves the tour with the shell’s retry, and resumes afterward', async () => {
    const fake = installFakeApi('priya')
    installAssistantApi()
    let puts = 0
    let works = false
    server.use(
      http.put(SWITCH(), async ({ request }) => {
        puts += 1
        if (!works) {
          return HttpResponse.json(
            { type: 'about:blank', title: 'Down', status: 500, instance: '/' },
            { status: 500 },
          )
        }
        const { persona } = (await request.json()) as { persona: Persona }
        fake.signIn(persona)
        return HttpResponse.json((await import('@/test/fixtures')).meFor(persona))
      }),
    )
    useTourStore.setState({ started: true, active: true, step: 1, sent: [], entering: true })
    const { user } = renderApp({ at: '/ask' })

    expect(await screen.findByText(/We couldn.t switch to Mateo/)).toBeInTheDocument()
    // No loop: wait long enough for a retry to show itself.
    await new Promise((resolve) => setTimeout(resolve, 300))
    expect(puts).toBe(1)
    expect(useTourStore.getState()).toMatchObject({ started: true, active: false, step: 1 })

    works = true
    await user.click(screen.getByRole('button', { name: /Switch persona$/ }))
    await user.click(await screen.findByRole('menuitem', { name: /Resume the tour/ }))
    await mark(/Same question, another state/)
    expect(puts).toBe(2)
    expect(personaSwitcher()).toHaveAccessibleName(/^Mateo Alvarez/)
  })

  it('does not count a switch the shell refused, and tries it once the other change is done', async () => {
    const fake = installFakeApi('priya')
    installAssistantApi()
    let puts = 0
    server.use(
      http.put(SWITCH(), async ({ request }) => {
        puts += 1
        const { persona } = (await request.json()) as { persona: Persona }
        fake.signIn(persona)
        return HttpResponse.json((await import('@/test/fixtures')).meFor(persona))
      }),
    )
    useTourStore.setState({ started: true, active: true, step: 1, sent: [], entering: false })
    const { queryClient } = renderApp({ at: '/ask' })
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    // An identity change started elsewhere, which the shell's own switcher knows nothing about.
    let finish = () => {}
    const other = queryClient
      .getMutationCache()
      .build(queryClient, {
        mutationKey: getEndSessionMutationKey(),
        mutationFn: () => new Promise<null>((resolve) => (finish = () => resolve(null))),
      })
      .execute(undefined)
    act(() => useTourStore.setState({ entering: true }))
    await new Promise((resolve) => setTimeout(resolve, 150))
    expect(puts).toBe(0)
    expect(useTourStore.getState()).toMatchObject({ active: true, switchTried: false })
    finish()
    await other
    await mark(/Same question, another state/)
    expect(puts).toBe(1)
  })

  it('tries a switch that succeeds into the wrong persona once, then leaves the tour', async () => {
    installFakeApi('priya')
    installAssistantApi()
    let puts = 0
    server.use(
      http.put(SWITCH(), async () => {
        puts += 1
        // The server answers, but with the person the visitor already was.
        return HttpResponse.json((await import('@/test/fixtures')).meFor('priya'))
      }),
    )
    useTourStore.setState({ started: true, active: true, step: 1, sent: [], entering: true })
    renderApp({ at: '/ask' })
    await waitFor(() => expect(useTourStore.getState().active).toBe(false))
    await new Promise((resolve) => setTimeout(resolve, 300))
    expect(puts).toBe(1)
    expect(useTourStore.getState()).toMatchObject({ started: true, active: false, step: 1 })
  })

  it('does not switch for a step that continues the conversation as the same person', async () => {
    installFakeApi('marcus')
    installAssistantApi()
    useTourStore.setState({ started: true, active: true, step: 3, sent: [], entering: false })
    const { user } = renderApp({ at: '/ask' })
    await mark(/Decide as the manager/)
    await user.click(screen.getByRole('button', { name: 'Skip this step' }))
    await mark(/Ask about someone’s absence/)
    expect(personaSwitcher()).toHaveAccessibleName(/^Marcus Bell/)
    expect(screen.queryByText(/^Switching to/)).not.toBeInTheDocument()
  })
})

describe('leaving, resuming, and ending', () => {
  it('leaves with the X: the toast, the coach mark gone, focus back in the composer, the step kept', async () => {
    const { user } = setup('priya', 0)
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    await mark(/Ask a policy question/)
    await user.click(screen.getByRole('button', { name: 'Leave the tour' }))
    expect(screen.queryByRole('dialog', { name: /Ask a policy question/ })).not.toBeInTheDocument()
    await waitFor(() => expect(toast()).toHaveTextContent(LEFT))
    expect(useTourStore.getState()).toMatchObject({ started: true, active: false, step: 0 })
    expect(screen.getByRole('textbox', { name: 'Ask Open Door' })).toHaveFocus()
  })

  it('leaves with Escape from anywhere on the page', async () => {
    const { user } = setup('priya', 0)
    await mark(/Ask a policy question/)
    await user.keyboard('{Escape}')
    await waitFor(() => expect(toast()).toHaveTextContent(LEFT))
    expect(screen.queryByRole('dialog', { name: /Ask a policy question/ })).not.toBeInTheDocument()
    expect(useTourStore.getState().active).toBe(false)
  })

  it('offers Resume with the step and Start over once left, and resumes as the step’s persona', async () => {
    const { user } = setup('priya', 1, { active: false })
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    expect(screen.queryByRole('dialog', { name: /Same question/ })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Switch persona$/ }))
    const resume = await screen.findByRole('menuitem', { name: /Resume the tour/ })
    expect(resume).toHaveTextContent('Step 2 of 10')
    expect(screen.getByRole('menuitem', { name: 'Start the tour over' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Take the tour' })).not.toBeInTheDocument()
    await user.click(resume)
    await mark(/Same question, another state/)
    expect(personaSwitcher()).toHaveAccessibleName(/^Mateo Alvarez/)
  })

  it('offers only Start over in the menu while the tour is showing, with nothing to resume', async () => {
    const { user } = setup('mateo', 1)
    await mark(/Same question, another state/)
    await user.click(screen.getByRole('button', { name: /Switch persona$/ }))
    expect(await screen.findByRole('menuitem', { name: 'Start the tour over' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /Resume the tour/ })).not.toBeInTheDocument()
  })

  it('leaves the tour when the visitor switches persona themselves, keeping the step', async () => {
    const { user } = setup('priya', 0)
    await mark(/Ask a policy question/)
    await user.click(screen.getByRole('button', { name: /Switch persona$/ }))
    await user.click(await screen.findByRole('menuitemradio', { name: /^Marcus / }))
    await screen.findByRole('heading', { level: 1, name: /Marcus/ })
    expect(screen.queryByRole('dialog', { name: /Ask a policy question/ })).not.toBeInTheDocument()
    expect(useTourStore.getState()).toMatchObject({ started: true, active: false, step: 0 })
  })

  it('resumes the step after a reload', async () => {
    installFakeApi('mateo')
    installAssistantApi()
    sessionStorage.setItem(
      'od.tour',
      JSON.stringify({
        state: {
          started: true,
          active: true,
          step: 1,
          sent: [0],
          turnId: null,
          lost: false,
          outcome: null,
          entering: false,
        },
        version: 3,
      }),
    )
    await useTourStore.persist.rehydrate()
    renderApp({ at: '/ask' })
    const card = await mark(/Same question, another state/)
    expect(within(card).getByText(/sent$/, { selector: 'span' })).toBeInTheDocument()
  })

  it('ends the tour with "Keep exploring as Dana" on the end card', async () => {
    installFakeApi('dana')
    installFakeConsole()
    useTourStore.setState({ started: true, active: true, step: 9, sent: [], entering: false })
    const { user } = renderApp({ at: '/console' })
    const card = await mark(/That’s the tour/)
    expect(within(card).getByText('Step 10 of 10')).toBeInTheDocument()
    await user.click(within(card).getByRole('button', { name: 'Keep exploring as Dana' }))
    expect(screen.queryByRole('dialog', { name: /That’s the tour/ })).not.toBeInTheDocument()
    expect(useTourStore.getState().started).toBe(false)
    await user.click(screen.getByRole('button', { name: /Switch persona$/ }))
    expect(await screen.findByRole('menuitem', { name: 'Take the tour' })).toBeInTheDocument()
  })

  it('ends the tour and opens the persona menu with "Choose who to be"', async () => {
    installFakeApi('dana')
    installFakeConsole()
    useTourStore.setState({ started: true, active: true, step: 9, sent: [], entering: false })
    const { user } = renderApp({ at: '/console' })
    const card = await mark(/That’s the tour/)
    await user.click(within(card).getByRole('button', { name: 'Choose who to be' }))
    expect(await screen.findByRole('menu')).toBeInTheDocument()
    expect(screen.getByRole('menuitemradio', { name: /^Priya / })).toBeInTheDocument()
    expect(useTourStore.getState().started).toBe(false)
    expect(screen.queryByRole('dialog', { name: /That’s the tour/ })).not.toBeInTheDocument()
  })
})

describe('starting from the persona menu', () => {
  it('asks first, keeps the old sandbox, and starts a new one as Priya at step 1', async () => {
    const fake = installFakeApi('marcus')
    installAssistantApi()
    const posted: unknown[] = []
    server.use(
      http.post(`${window.location.origin}/api/v1/sandboxes`, async ({ request }) => {
        posted.push(await request.json())
        fake.signIn('priya')
        return HttpResponse.json(
          {
            tenant: { id: 't', expiresAt: '2026-10-06T12:00:00Z' },
            me: (await import('@/test/fixtures')).meFor('priya'),
          },
          { status: 201 },
        )
      }),
    )
    const { user } = renderApp({ at: '/ask' })
    await user.click(await screen.findByRole('button', { name: /Switch persona$/ }))
    await user.click(await screen.findByRole('menuitem', { name: 'Take the tour' }))
    const dialog = await screen.findByRole('alertdialog', { name: 'Start the tour?' })
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toHaveFocus()
    expect(dialog).toHaveTextContent('Your current sandbox stays until it expires.')
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(posted).toEqual([])
    expect(useTourStore.getState().started).toBe(false)

    await user.click(screen.getByRole('button', { name: /Switch persona$/ }))
    await user.click(await screen.findByRole('menuitem', { name: 'Take the tour' }))
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', {
        name: 'Start the tour',
      }),
    )
    await mark(/Ask a policy question/)
    expect(posted).toEqual([{ persona: 'priya', turnstileToken: DUMMY_TURNSTILE_TOKEN }])
    expect(personaSwitcher()).toHaveAccessibleName(/^Priya Raman/)
    expect(useTourStore.getState()).toMatchObject({ started: true, active: true, step: 0 })
    await act(async () => {})
  })
})
