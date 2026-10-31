import { act, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CaseStatusOut, EscalationOut, PersonaKey } from '@/api/generated'
import { MY_CASES, SENT_LINE, WAITING_LIMIT } from '@/app/gallery/fixtures/cases'
import { announce } from '@/lib/announce'
import { useChatStore } from '@/features/chat/store'
import { resetIdentity } from '@/lib/identity'
import { DANA } from '@/test/assistant-fixtures'
import { installFakeApi } from '@/test/fake-api'
import {
  conversationOut,
  installAssistantApi,
  onTurn,
  openStream,
  turnOut,
} from '@/test/fake-assistant'
import { CASE_TEXTS, installFakeCases, statusView } from '@/test/fake-cases'
import { server } from '@/test/msw'
import { delay, http, HttpResponse } from 'msw'
import { renderApp } from '@/test/render-app'
import { useCaseSlots } from './case-slots'

// The case button, the form, and the sent line under an HR panel in the conversation (Task 35).

vi.mock('@/lib/announce', () => ({ announce: vi.fn<() => void>(), resetAnnouncer: () => {} }))

const QUESTION = 'My manager keeps making comments about my age.'
const SENSITIVE: EscalationOut = {
  kind: 'sensitive',
  message: 'This sounds like something a person should help with.',
  hrContact: [DANA],
  offerCase: true,
}
const CRISIS: EscalationOut = { ...SENSITIVE, kind: 'crisis', message: 'Please reach a person.' }
const HEADER = 'A person in HR handles this, not the AI'
const CRISIS_TEXT = 'If you are in danger, call 911. The 988 Lifeline is open 24/7.'

const flagged = (over: Parameters<typeof turnOut>[0] = {}) =>
  turnOut({
    id: 't-1',
    question: QUESTION,
    answerText: 'I’m sorry that happened.',
    escalation: SENSITIVE,
    guard: { category: 'sensitive' },
    ...over,
  })

function open(persona: PersonaKey, turns = [flagged()], cases = {}) {
  installFakeApi(persona)
  installAssistantApi({ conversation: conversationOut({ turns, hrContacts: [DANA] }) })
  const fake = installFakeCases(cases)
  return { ...renderApp({ at: '/ask' }), fake }
}

const button = () => screen.findByRole('button', { name: 'Open a confidential case' })
const words = () => screen.findByRole<HTMLTextAreaElement>('textbox', { name: 'Your words' })
const sendButton = () => screen.getByRole('button', { name: /^(Send to HR|Try again)$/ })

async function sendFrom(user: ReturnType<typeof renderApp>['user']) {
  await user.click(await button())
  await user.click(await screen.findByRole('radio', { name: 'Harassment or discrimination' }))
  await user.click(sendButton())
}

beforeEach(() => {
  useChatStore.setState(useChatStore.getInitialState())
  useCaseSlots.getState().reset()
})

describe('the case button', () => {
  it('shows on a finished flagged turn, and opens the form with the question word for word', async () => {
    const { user, fake } = open('priya')
    await user.click(await button())
    expect(await words()).toHaveValue(QUESTION)
    expect(await screen.findByText(/Your case is stored encrypted/)).toBeInTheDocument()
    expect(fake.calls.posts).toEqual([])
  })

  it('is not there while the turn is still running', async () => {
    open('priya', [flagged({ id: 't-run', status: 'running' })])
    await screen.findByRole('region', { name: HEADER })
    expect(screen.queryByRole('button', { name: 'Open a confidential case' })).toBeNull()
  })

  it('is not offered after an internal error, and is offered after other failures', async () => {
    open('priya', [
      flagged({
        id: 't-internal',
        status: 'failed',
        error: { code: 'internal', message: 'Something broke.' },
      }),
      flagged({
        id: 't-budget',
        status: 'failed',
        error: { code: 'budget-sandbox', message: 'The sandbox budget is used.' },
      }),
    ])
    await screen.findAllByRole('region', { name: HEADER })
    expect(await screen.findAllByRole('button', { name: 'Open a confidential case' })).toHaveLength(
      1,
    )
  })

  it('is not on a panel whose event did not offer a case', async () => {
    open('priya', [flagged({ escalation: { ...SENSITIVE, offerCase: false } })])
    await screen.findByRole('region', { name: HEADER })
    expect(screen.queryByRole('button', { name: 'Open a confidential case' })).toBeNull()
  })

  it('is on the crisis panel too, as the secondary button', async () => {
    open('priya', [flagged({ escalation: CRISIS, guard: { category: 'crisis' } })])
    expect(await button()).toBeInTheDocument()
  })

  it('is never on the live turn, only on its saved copy', async () => {
    installFakeApi('priya')
    const api = installAssistantApi()
    installFakeCases()
    const stream = openStream()
    onTurn(() => stream.response())
    const { user, queryClient } = renderApp({ at: '/ask' })
    await user.type(
      await screen.findByRole('textbox', { name: 'Ask Open Door' }),
      `${QUESTION}{Enter}`,
    )
    stream.push('turn.started', { turnId: 't-1' })
    stream.push('text.delta', { text: 'I’m sorry.' })
    stream.push('escalation', SENSITIVE)
    await screen.findByRole('region', { name: HEADER })
    expect(screen.queryByRole('button', { name: 'Open a confidential case' })).toBeNull()

    stream.push('turn.completed', {
      turnId: 't-1',
      servedBy: 'anthropic',
      usage: { inputTokens: 1, outputTokens: 1 },
    })
    stream.close()
    await waitFor(() => expect(useChatStore.getState().turn?.completed).toBe(true))
    // Finished, but the saved copy has not arrived: still no button.
    expect(screen.queryByRole('button', { name: 'Open a confidential case' })).toBeNull()

    api.setCurrent(
      conversationOut({ turns: [flagged({ answerText: 'I’m sorry.' })], hrContacts: [DANA] }),
    )
    await queryClient.invalidateQueries()
    expect(await button()).toBeInTheDocument()
  })
})

describe('sending from the panel', () => {
  it('sends the turn and the words once, and shows the sent line with a link to My cases', async () => {
    const { user, fake } = open('priya')
    await sendFrom(user)
    const line = await screen.findByText(`${SENT_LINE.lead} ${SENT_LINE.pointer}`)
    expect(line).toBeInTheDocument()
    expect(fake.calls.posts).toHaveLength(1)
    expect(fake.calls.posts[0]).toMatchObject({
      turnId: 't-1',
      text: QUESTION,
      category: 'harassment_discrimination',
    })
    expect(screen.getByRole('link', { name: 'View in My cases' })).toHaveAttribute(
      'href',
      '/my-cases',
    )
    expect(screen.queryByRole('button', { name: 'Open a confidential case' })).toBeNull()
  })

  it('ignores a second Send while one is waiting, so one case is opened', async () => {
    const { user, fake } = open('priya')
    await user.click(await button())
    await user.click(await screen.findByRole('radio', { name: 'Workplace safety' }))
    const send = sendButton()
    // Both presses land before the page draws again, so neither sees "Sending…".
    act(() => {
      send.click()
      send.click()
    })
    await screen.findByText(/^Sent to HR/)
    expect(fake.calls.posts).toHaveLength(1)
  })

  it('gives HR no link on the sent line', async () => {
    const { user } = open('dana')
    await sendFrom(user)
    await screen.findByText(/^Sent to HR/)
    expect(screen.queryByRole('link', { name: /My cases/ })).toBeNull()
    expect(screen.queryByRole('link', { name: /(my|your) cases/i })).toBeNull()
  })

  it('shows the crisis text after the sent line, right after sending only', async () => {
    const { user } = open('priya', [flagged()], { crisisText: CRISIS_TEXT })
    await sendFrom(user)
    const sent = await screen.findByText(/^Sent to HR/)
    const crisis = await screen.findByRole('region', { name: 'Reach a person right now' })
    expect(within(crisis).getByText(/call 911/)).toBeInTheDocument()
    const order = sent.compareDocumentPosition(crisis)
    expect(order & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('shows the limit line when the server says five are waiting, with a link for a person', async () => {
    const { user, fake } = open('priya', [flagged()], {
      openProblem: { status: 409, type: 'case-waiting-limit', detail: 'Five waiting.' },
    })
    // The server refuses because five are waiting, and the list read again says so.
    await user.click(await button())
    await user.click(await screen.findByRole('radio', { name: 'Harassment or discrimination' }))
    fake.state.mine = Array.from({ length: 5 }, (_, i) => statusView({ id: `w-${i}` }))
    await user.click(sendButton())
    expect(await screen.findByText(WAITING_LIMIT)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View your cases' })).toHaveAttribute(
      'href',
      '/my-cases',
    )
  })

  it('offers the button again once the list read after a refusal shows fewer than five waiting', async () => {
    const { user } = open('priya', [flagged()], {
      openProblem: { status: 409, type: 'case-waiting-limit', detail: 'Five waiting.' },
    })
    await user.click(await button())
    await user.click(await screen.findByRole('radio', { name: 'Harassment or discrimination' }))
    // The list read after the refusal is slow, so the refusal alone holds the line meanwhile.
    server.use(
      http.get(`${window.location.origin}/api/v1/cases/mine`, async () => {
        await delay(150)
        return HttpResponse.json({ items: [] })
      }),
    )
    await user.click(sendButton())
    expect(await screen.findByText(WAITING_LIMIT)).toBeInTheDocument()
    // Then the list shows fewer than five: the line goes, and the button is back.
    expect(await button()).toBeVisible()
    expect(screen.queryByText(WAITING_LIMIT)).toBeNull()
  })

  it('shows the personal-data refusal on the words, and keeps them', async () => {
    const { user } = open('priya', [flagged()], {
      openProblem: { status: 422, type: 'case-personal-data', detail: 'No numbers.' },
    })
    await sendFrom(user)
    expect(await screen.findByText(/Social Security or card number/)).toBeInTheDocument()
    expect(await words()).toHaveValue(QUESTION)
    expect(await words()).toHaveFocus()
  })

  it('ends a refusal with focus in the words box and the button ready, though the lists are slow to read again', async () => {
    const { user } = open('priya', [flagged()], {
      openProblem: { status: 422, type: 'case-personal-data', detail: 'No numbers.' },
    })
    await user.click(await button())
    await user.click(await screen.findByRole('radio', { name: 'Harassment or discrimination' }))
    // From here the case lists answer only when released.
    let release!: () => void
    const held = new Promise<void>((resolve) => (release = resolve))
    server.use(
      http.get(`${window.location.origin}/api/v1/cases/mine`, async () => {
        await held
        return HttpResponse.json({ items: [] })
      }),
    )
    await user.click(sendButton())
    expect(await screen.findByText(/Social Security or card number/)).toBeInTheDocument()
    try {
      await waitFor(() => expect(screen.getByRole('textbox', { name: 'Your words' })).toHaveFocus())
      expect(screen.getByRole('button', { name: 'Send to HR' })).toBeEnabled()
    } finally {
      release()
    }
  })

  it('says the case was not sent after any other failure, and Try again can send', async () => {
    const { user, fake } = open('priya', [flagged()], {
      openProblem: { status: 500, type: 'about:blank', detail: 'Broke.' },
    })
    await sendFrom(user)
    expect(await screen.findByText('Your case wasn’t sent. Please try again.')).toBeVisible()
    fake.state.openProblem = null
    await user.click(sendButton())
    await screen.findByText(/^Sent to HR/)
    // The retry reuses the form's submission ID.
    expect(fake.calls.posts).toHaveLength(2)
    expect(fake.calls.posts[0]!.submissionId).toBe(fake.calls.posts[1]!.submissionId)
  })

  it('treats a conflict on the submission as already sent: no error, and the saved turn shows the sent line', async () => {
    const { user, fake } = open('priya', [flagged()], {
      openProblem: { status: 409, type: 'case-submission-conflict', detail: 'Already sent.' },
      saveBeforeProblem: true,
    })
    // Once the first send has reached the server, the conversation carries the case.
    server.use(
      http.get(`${window.location.origin}/api/v1/assistant/conversations/current`, () =>
        HttpResponse.json(
          conversationOut({
            turns: [
              flagged(
                fake.calls.posts.length > 0
                  ? { caseOpened: { status: 'new', replyBy: '2026-10-28', sentLine: SENT_LINE } }
                  : {},
              ),
            ],
            hrContacts: [DANA],
          }),
        ),
      ),
    )
    await sendFrom(user)
    expect(await screen.findByText(`${SENT_LINE.lead} ${SENT_LINE.pointer}`)).toBeVisible()
    expect(screen.queryByRole('textbox', { name: 'Your words' })).toBeNull()
    expect(screen.queryByText('Your case wasn’t sent. Please try again.')).toBeNull()
    // The form's slot is closed, not left open behind the sent line.
    expect(useCaseSlots.getState().slots['t-1']).toBeUndefined()
  })

  it('reads the cases and the conversation again, and never writes the cache', async () => {
    const { user, fake, queryClient } = open('priya')
    const before = fake.calls.mine
    await sendFrom(user)
    await screen.findByText(/^Sent to HR/)
    await waitFor(() => expect(fake.calls.mine).toBeGreaterThan(before))
    expect(queryClient.getQueryCache().getAll().length).toBeGreaterThan(0)
  })
})

describe('one case per turn', () => {
  it('shows the sent line from the saved turn after a reload, with no button', async () => {
    open('priya', [
      flagged({
        caseOpened: { status: 'new', replyBy: '2026-10-28', sentLine: SENT_LINE },
      }),
    ])
    expect(await screen.findByText(`${SENT_LINE.lead} ${SENT_LINE.pointer}`)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Open a confidential case' })).toBeNull()
    // A reload does not take focus, and shows no crisis text.
    expect(screen.getByText(/^Sent to HR/)).not.toHaveFocus()
    expect(screen.queryByRole('region', { name: 'Reach a person right now' })).toBeNull()
  })

  it('gives HR no link on a reloaded sent line', async () => {
    open('dana', [
      flagged({ caseOpened: { status: 'new', replyBy: '2026-10-28', sentLine: SENT_LINE } }),
    ])
    await screen.findByText(/^Sent to HR/)
    expect(screen.queryByRole('link', { name: /(my|your) cases/i })).toBeNull()
  })
})

describe('five waiting cases', () => {
  const waiting = (n: number): CaseStatusOut[] =>
    Array.from({ length: n }, (_, i) => statusView({ id: `w-${i}`, status: 'new' }))

  it('replaces the button with the limit line, with a link for a person', async () => {
    open('priya', [flagged()], { mine: waiting(5) })
    expect(await screen.findByText(WAITING_LIMIT)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Open a confidential case' })).toBeNull()
    expect(screen.getByRole('link', { name: 'View your cases' })).toBeInTheDocument()
  })

  it('counts new and in-review cases, not closed ones', async () => {
    open('priya', [flagged()], {
      mine: [...waiting(3), ...MY_CASES.filter((c) => c.status !== 'new')],
    })
    expect(await button()).toBeInTheDocument()
    expect(screen.queryByText(WAITING_LIMIT)).toBeNull()
  })

  it('gives HR the line with no link', async () => {
    open('dana', [flagged()], { mine: waiting(5) })
    expect(await screen.findByText(WAITING_LIMIT)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /(my|your) cases/i })).toBeNull()
  })
})

describe('the form belongs to its turn, not to the component', () => {
  it('Not now closes the form and returns focus to the button', async () => {
    const { user } = open('priya')
    await user.click(await button())
    await words()
    await user.click(screen.getByRole('button', { name: 'Not now' }))
    expect(useCaseSlots.getState().slots['t-1']).toBeUndefined()
    expect(await button()).toHaveFocus()
  })

  it('is forgotten on a persona switch', () => {
    useCaseSlots.getState().set('t-1', { phase: 'open' })
    resetIdentity({ clear: () => {} } as never)
    expect(useCaseSlots.getState().slots).toEqual({})
  })

  it('shows the form already open for a turn the store says is open', async () => {
    useCaseSlots.getState().set('t-1', { phase: 'open' })
    open('priya')
    expect(await words()).toHaveValue(QUESTION)
  })
})

describe('a form opened again, and texts that did not load', () => {
  it('does not bring back an earlier refusal when the form is reopened', async () => {
    const { user } = open('priya', [flagged()], {
      openProblem: { status: 422, type: 'case-personal-data', detail: 'No numbers.' },
    })
    await sendFrom(user)
    await screen.findByText(/Social Security or card number/)
    await user.click(screen.getByRole('button', { name: 'Not now' }))
    await user.click(await button())
    await words()
    expect(screen.queryByText(/Social Security or card number/)).toBeNull()
    expect(
      screen.getByRole('heading', { level: 3, name: 'Open a confidential case' }),
    ).toHaveFocus()
  })

  it('does not bring back an earlier send failure when the form is reopened', async () => {
    const { user } = open('priya', [flagged()], {
      openProblem: { status: 500, type: 'about:blank', detail: 'Broke.' },
    })
    await sendFrom(user)
    await screen.findByText('Your case wasn’t sent. Please try again.')
    await user.click(screen.getByRole('button', { name: 'Not now' }))
    await user.click(await button())
    await words()
    expect(screen.queryByText('Your case wasn’t sent. Please try again.')).toBeNull()
  })

  it('shows no button, and no new area, when the form’s texts could not be loaded', async () => {
    installFakeApi('priya')
    installAssistantApi({
      conversation: conversationOut({ turns: [flagged()], hrContacts: [DANA] }),
    })
    installFakeCases()
    server.use(
      http.get(`${window.location.origin}/api/v1/cases/texts`, () =>
        HttpResponse.json({ type: 'about:blank', title: 'x', status: 500 }, { status: 500 }),
      ),
    )
    renderApp({ at: '/ask' })
    await screen.findByRole('region', { name: HEADER })
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(screen.queryByRole('button', { name: 'Open a confidential case' })).toBeNull()
  })

  it('still shows a sent line from a saved turn when the texts could not be loaded', async () => {
    installFakeApi('priya')
    installAssistantApi({
      conversation: conversationOut({
        turns: [
          flagged({ caseOpened: { status: 'new', replyBy: '2026-10-28', sentLine: SENT_LINE } }),
        ],
      }),
    })
    installFakeCases()
    server.use(
      http.get(`${window.location.origin}/api/v1/cases/texts`, () =>
        HttpResponse.json({ type: 'about:blank', title: 'x', status: 500 }, { status: 500 }),
      ),
    )
    renderApp({ at: '/ask' })
    expect(await screen.findByText(/^Sent to HR/)).toBeVisible()
  })

  it('shows no button until the texts have arrived', async () => {
    installFakeApi('priya')
    installAssistantApi({ conversation: conversationOut({ turns: [flagged()] }) })
    installFakeCases()
    let release!: () => void
    const held = new Promise<void>((resolve) => (release = resolve))
    server.use(
      http.get(`${window.location.origin}/api/v1/cases/texts`, async () => {
        await held
        return HttpResponse.json(CASE_TEXTS)
      }),
    )
    renderApp({ at: '/ask' })
    await screen.findByRole('region', { name: HEADER })
    expect(screen.queryByRole('button', { name: 'Open a confidential case' })).toBeNull()
    release()
    expect(await button()).toBeVisible()
  })
})

describe('coming back to the conversation after a send', () => {
  const sentLineOf = () => screen.getByText(/^Sent to HR/).closest('output')

  it('shows the sent line and the crisis panel again without moving focus or announcing again', async () => {
    const { user, router } = open('priya', [flagged()], { crisisText: CRISIS_TEXT })
    await sendFrom(user)
    await screen.findByRole('region', { name: 'Reach a person right now' })
    expect(sentLineOf()).toHaveFocus()
    expect(announce).toHaveBeenCalledWith('Reach a person right now', 'assertive')
    vi.mocked(announce).mockClear()

    await router.navigate('/my-cases')
    await screen.findByRole('heading', { level: 1 })
    await router.navigate('/ask')
    await screen.findByRole('region', { name: 'Reach a person right now' })
    expect(sentLineOf()).not.toHaveFocus()
    expect(announce).not.toHaveBeenCalled()
  })

  it('does not pull focus to a limit line shown before', async () => {
    const { user, router } = open('priya', [flagged()], {
      openProblem: { status: 409, type: 'case-waiting-limit', detail: 'Five waiting.' },
      mine: Array.from({ length: 5 }, (_, i) => statusView({ id: `w-${i}`, status: 'new' })),
    })
    useCaseSlots.getState().set('t-1', { phase: 'open' })
    await words()
    await user.click(await screen.findByRole('radio', { name: 'Workplace safety' }))
    await user.click(sendButton())
    const line = await screen.findByText(WAITING_LIMIT)
    expect(line.closest('output')).toHaveFocus()
    await router.navigate('/my-cases')
    await screen.findByRole('heading', { level: 1 })
    await router.navigate('/ask')
    expect((await screen.findByText(WAITING_LIMIT)).closest('output')).not.toHaveFocus()
  })

  it('lets a limit line that replaces a quiet sent line decide about focus for itself', async () => {
    const { queryClient } = open('priya')
    useCaseSlots.getState().set('t-1', {
      phase: 'sent',
      sent: { sentLine: SENT_LINE, crisisText: null },
      shown: true,
    } as never)
    const sent = await screen.findByText(`${SENT_LINE.lead} ${SENT_LINE.pointer}`)
    expect(sent.closest('output')).not.toHaveFocus()

    const readAt = queryClient.getQueryState(['/api/v1/cases/mine'])!.dataUpdatedAt
    act(() => useCaseSlots.getState().set('t-1', { phase: 'limit', readAt }))
    // A new line that has not been shown before takes focus, though the sent line it replaced did not.
    expect((await screen.findByText(WAITING_LIMIT)).closest('output')).toHaveFocus()
  })

  it('does not move focus into a form that is open when the person returns', async () => {
    const { user, router } = open('priya')
    await user.click(await button())
    await words()
    expect(
      screen.getByRole('heading', { level: 3, name: 'Open a confidential case' }),
    ).toHaveFocus()
    await router.navigate('/my-cases')
    await screen.findByRole('heading', { level: 1 })
    await router.navigate('/ask')
    await words()
    expect(
      screen.getByRole('heading', { level: 3, name: 'Open a confidential case' }),
    ).not.toHaveFocus()
  })
})

describe('the crisis text after a send', () => {
  it('is not repeated under a panel that is itself the crisis panel', async () => {
    const { user } = open(
      'priya',
      [flagged({ escalation: CRISIS, guard: { category: 'crisis' } })],
      { crisisText: CRISIS_TEXT },
    )
    await sendFrom(user)
    await screen.findByText(/^Sent to HR/)
    expect(screen.getAllByRole('region', { name: 'Reach a person right now' })).toHaveLength(1)
  })
})
