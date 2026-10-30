import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ConversationOut, EscalationOut, TurnOut } from '@/api/generated'
import { citation, DANA, toolCall } from '@/test/assistant-fixtures'
import { installFakeApi } from '@/test/fake-api'
import {
  TEXTS,
  TURN_ID,
  conversationOut,
  eventStream,
  installAssistantApi,
  onFeedback,
  onTurn,
  openStream,
  problemResponse,
  turnOut,
} from '@/test/fake-assistant'
import { renderApp } from '@/test/render-app'
import { server } from '@/test/msw'
import { useChatStore } from './store'

// The conversation page at /ask, against the fake API: what the first question does to the home, what
// a reload shows, and every state a turn can be in. The source panel has its own file
// (source-panel.test.tsx).

const announceMock = vi.hoisted(() => vi.fn<(text: string, politeness?: string) => void>())
vi.mock('@/lib/announce', () => ({ announce: announceMock, resetAnnouncer: () => {} }))

const ANSWER = 'You get 40 hours of sick leave. Tell your manager early.'
const FIRST_END = ANSWER.indexOf('.') + 1
const CA = citation({
  marker: 1,
  sectionId: 'CA-4.3',
  passageId: 'p2',
  offsetUtf16: FIRST_END,
  groupName: 'California addendum',
})
const COMPANY = citation({
  marker: 2,
  sectionId: '4.3',
  passageId: 'p1',
  offsetUtf16: ANSWER.length,
  title: 'Sick leave',
  groupName: 'Time off',
})

function cited(overrides: Partial<TurnOut> = {}): TurnOut {
  return turnOut({
    answerText: ANSWER,
    citations: [CA, COMPANY],
    toolCalls: [toolCall()],
    sections: [
      {
        sectionId: 'CA-4.3',
        passageIds: ['p2'],
        title: 'Sick leave',
        groupName: 'California addendum',
      },
      { sectionId: '4.3', passageIds: ['p1'], title: 'Sick leave', groupName: 'Time off' },
    ],
    ...overrides,
  })
}

const composer = () => screen.findByRole('textbox', { name: 'Ask Open Door' })
const thanks = 'Thanks for the feedback.'
const SENSITIVE: EscalationOut = {
  kind: 'sensitive',
  message: 'This sounds like something a person should help with.',
  hrContact: [DANA],
  offerCase: false,
}
const SENSITIVE_HEADER = 'A person in HR handles this, not the AI'

function completedEvents(turnId: string, text: string) {
  return [
    ['turn.started', { turnId }],
    ['text.delta', { text }],
    [
      'turn.completed',
      { turnId, servedBy: 'anthropic', usage: { inputTokens: 1, outputTokens: 1 } },
    ],
  ] as [string, unknown][]
}

beforeEach(() => {
  useChatStore.setState(useChatStore.getInitialState())
  announceMock.mockClear()
})
afterEach(() => {
  vi.useRealTimers()
})

function signedInWith(conversation: ConversationOut | null) {
  installFakeApi('priya')
  return installAssistantApi({ conversation })
}

describe('the home and the conversation', () => {
  it('shows the home with no conversation, and waits for the texts and the conversation first', async () => {
    installFakeApi('priya')
    const api = installAssistantApi()
    renderApp({ at: '/ask' })
    expect(screen.queryByRole('textbox', { name: 'Ask Open Door' })).not.toBeInTheDocument()
    expect(await composer()).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/Priya/)
    expect(api.requests.texts).toBe(1)
    expect(api.requests.current).toBeGreaterThanOrEqual(1)
  })

  it('turns the home into the conversation at the first question, and keeps focus in the composer', async () => {
    const api = signedInWith(null)
    onTurn(() => {
      api.setCurrent(
        conversationOut({
          turns: [cited({ id: 't-1', question: 'How many sick days do I get?' })],
        }),
      )
      return eventStream(...completedEvents('t-1', ANSWER))
    })
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'How many sick days do I get?{Enter}')

    // The greeting and "Try asking" go, and the thread and the follow-up box come.
    expect(
      await screen.findByText('How many sick days do I get?', {
        selector: '[data-slot="user-message"]',
      }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 1 })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Try asking' })).not.toBeInTheDocument()
    const box = await composer()
    expect(box).toHaveAttribute('placeholder', 'Ask a follow-up question')
    expect(box).toHaveFocus()
    expect(await screen.findByText(/You get 40 hours of sick leave\./)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start a new conversation' })).toBeInTheDocument()
  })

  it('shows the conversation from the server after a reload, a stopped answer included', async () => {
    signedInWith(
      conversationOut({
        turns: [
          cited({ id: 't-1' }),
          turnOut({
            id: 't-2',
            question: 'And carry-over?',
            status: 'stopped',
            answerText: 'Unused sick leave does not',
            endedAt: null,
          }),
        ],
      }),
    )
    renderApp({ at: '/ask' })
    expect(
      await screen.findByText('How many sick days do I get?', {
        selector: '[data-slot="user-message"]',
      }),
    ).toBeInTheDocument()
    expect(screen.getByText(/Unused sick leave does not/)).toBeInTheDocument()
    expect(screen.getByText('Stopped')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask again' })).toBeInTheDocument()
    // The first answer is finished: it has its sources and feedback.
    expect(screen.getByRole('list', { name: 'Sources' })).toBeInTheDocument()
    expect(screen.getByText('Was this right?')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 1 })).not.toBeInTheDocument()
  })

  it('sends a stopped answer’s question again with Ask again', async () => {
    signedInWith(
      conversationOut({
        turns: [
          turnOut({ id: 't-2', question: 'And carry-over?', status: 'stopped', answerText: 'Un' }),
        ],
      }),
    )
    const posted = onTurn(() => eventStream(...completedEvents('t-3', 'Done.')))
    const { user } = renderApp({ at: '/ask' })
    await user.click(await screen.findByRole('button', { name: 'Ask again' }))
    await waitFor(() => expect(posted).toHaveLength(1))
    expect(posted[0]?.question).toBe('And carry-over?')
  })

  it('"Start a new conversation" posts, and the view goes back to the home', async () => {
    const api = signedInWith(conversationOut({ turns: [cited()] }))
    const { user } = renderApp({ at: '/ask' })
    await user.click(await screen.findByRole('button', { name: 'Start a new conversation' }))
    await waitFor(() => expect(api.requests.created).toBe(1))
    expect(await screen.findByRole('heading', { level: 1 })).toBeInTheDocument()
    expect(document.querySelector('[data-slot="user-message"]')).toBeNull()
    // Focus was on the button that went away: the new composer has it.
    await waitFor(async () => expect(await composer()).toHaveFocus())
  })

  it('shows the composer busy while a question waits for the new conversation, and a second Enter changes nothing', async () => {
    signedInWith(conversationOut({ turns: [cited()] }))
    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => (release = resolve))
    server.use(
      http.post(`${window.location.origin}/api/v1/assistant/conversations`, async () => {
        await gate
        return HttpResponse.json(conversationOut(), { status: 201 })
      }),
    )
    const posted = onTurn(() => eventStream(...completedEvents('t-2', 'Back.')))
    const { user } = renderApp({ at: '/ask' })
    await user.click(await screen.findByRole('button', { name: 'Start a new conversation' }))
    // The page is still the conversation (the new one is not created yet).
    await user.type(await composer(), 'Sick days?{Enter}')
    const ask = await screen.findByRole('button', { name: 'Ask' })
    await waitFor(() => expect(ask).toHaveAttribute('aria-busy', 'true'))
    await user.type(await composer(), '{Enter}')
    expect(posted).toEqual([])
    expect(screen.getByRole('button', { name: 'Ask' })).toHaveAttribute('aria-busy', 'true')
    release()
    await waitFor(() => expect(posted).toHaveLength(1))
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Ask' })).not.toHaveAttribute('aria-busy'),
    )
  })

  it('offers a new conversation when the API says this one cannot go on (409 conversation-outdated)', async () => {
    signedInWith(conversationOut({ turns: [cited()] }))
    onTurn(() =>
      problemResponse(409, 'conversation-outdated', 'This conversation uses an older assistant.'),
    )
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'Another question{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This conversation uses an older assistant.',
    )
    // The notice in the composer, besides the header's button.
    expect(screen.getAllByRole('button', { name: 'Start a new conversation' })).toHaveLength(2)
    expect(screen.getByText(/This conversation is getting long/)).toBeInTheDocument()
    // The question stays in the box.
    expect(await composer()).toHaveValue('Another question')
  })

  it('shows the long-conversation notice from the conversation’s own flag', async () => {
    signedInWith(conversationOut({ turns: [cited()], longHistory: true }))
    renderApp({ at: '/ask' })
    expect(await screen.findByText(/This conversation is getting long/)).toBeInTheDocument()
  })

  it('offers a new conversation from the conversation’s own historyTooLong flag', async () => {
    signedInWith(conversationOut({ turns: [cited()], historyTooLong: true }))
    renderApp({ at: '/ask' })
    expect(await screen.findByText(/This conversation is getting long/)).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Start a new conversation' })).toHaveLength(2)
  })

  it('says nothing on load for an outdated conversation: its words do not fit, and the send explains', async () => {
    signedInWith(conversationOut({ turns: [cited()], outdated: true }))
    renderApp({ at: '/ask' })
    await screen.findByText(/You get 40 hours/)
    expect(screen.queryByText(/This conversation is getting long/)).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Start a new conversation' })).toHaveLength(1)
  })

  it('does not show the notice for an ordinary conversation', async () => {
    signedInWith(conversationOut({ turns: [cited()] }))
    renderApp({ at: '/ask' })
    await screen.findByText(/You get 40 hours/)
    expect(screen.queryByText(/This conversation is getting long/)).not.toBeInTheDocument()
  })

  it('sends the HR contacts card under a not-found answer, and under no other', async () => {
    signedInWith(
      conversationOut({
        hrContacts: [DANA],
        turns: [
          turnOut({
            id: 't-1',
            question: 'Tuition?',
            answerText: 'I couldn’t find that.',
            notFound: true,
          }),
          cited({ id: 't-2' }),
        ],
      }),
    )
    renderApp({ at: '/ask' })
    const cards = await screen.findAllByText('HR contacts')
    expect(cards).toHaveLength(1)
    expect(screen.getByText('Dana Whitfield')).toBeInTheDocument()
    expect(screen.getByText('hr@juniperrow.example')).toBeInTheDocument()
  })
})

describe('sensitive and crisis turns', () => {
  it('shows a sensitive turn as the answer with its own feedback, then the panel, then the work capped at 680 px', async () => {
    signedInWith(
      conversationOut({
        turns: [
          turnOut({
            id: 't-1',
            question: 'My manager keeps making comments',
            answerText: 'I’m sorry that is happening.',
            guard: { category: 'sensitive' },
            escalation: SENSITIVE,
          }),
        ],
      }),
    )
    renderApp({ at: '/ask' })
    const panel = await screen.findByRole('region', { name: SENSITIVE_HEADER })
    expect(screen.getByText('I’m sorry that is happening.')).toBeInTheDocument()
    // The answer has "Was this right?"; the panel does not, and "Show your work" sits under it.
    expect(screen.getAllByText('Was this right?')).toHaveLength(1)
    expect(within(panel).queryByText('Was this right?')).not.toBeInTheDocument()
    const work = screen.getByRole('button', { name: 'Show your work' })
    const capped = work.closest('div.max-w-\\[680px\\]')
    expect(capped).not.toBeNull()
    expect(panel.compareDocumentPosition(capped!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    // Routed to HR, as the work lists it.
    await userEvent.setup().click(work)
    expect(screen.getByText('Routed to HR guidance')).toBeInTheDocument()
  })

  it('shows a crisis turn as the panel alone: no AI label, sources, or feedback', async () => {
    signedInWith(
      conversationOut({
        turns: [
          turnOut({
            id: 't-1',
            question: 'I want to hurt myself',
            status: 'crisis',
            answerText: '',
            guard: { category: 'crisis' },
            escalation: {
              kind: 'crisis',
              message: 'Call or text 988.',
              hrContact: [DANA],
              offerCase: false,
            },
          }),
        ],
      }),
    )
    renderApp({ at: '/ask' })
    expect(
      await screen.findByRole('region', { name: 'Reach a person right now' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByText('Open Door', { selector: '[data-slot="assistant-message"] *' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByText('Was this right?')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Show your work' })).not.toBeInTheDocument()
  })

  it('shows "can’t answer right now" with Try again, which asks the question again', async () => {
    signedInWith(
      conversationOut({
        turns: [
          turnOut({
            id: 't-1',
            question: 'How many sick days do I get?',
            status: 'guard_unavailable',
            answerText: '',
            guard: null,
            escalation: {
              kind: 'unavailable',
              message: 'We can’t answer right now.',
              hrContact: [DANA],
              offerCase: false,
            },
          }),
        ],
      }),
    )
    const posted = onTurn(() => eventStream(...completedEvents('t-2', 'Back.')))
    const { user } = renderApp({ at: '/ask' })
    await user.click(await screen.findByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(posted).toHaveLength(1))
    expect(posted[0]?.question).toBe('How many sick days do I get?')
  })
})

describe('a sensitive turn that ended some other way still shows its HR panel', () => {
  // A sensitive turn can fail (the budget ran out at the model call) or be cut off: sensitive
  // topics go to a person whatever happened to the answer (invariant 6).
  it('shows the error message and the sensitive panel for a failed turn, on every read', async () => {
    signedInWith(
      conversationOut({
        turns: [
          turnOut({
            id: 't-1',
            question: 'My manager keeps making comments',
            status: 'failed',
            answerText: '',
            error: { code: 'budget-sandbox', message: 'The sandbox budget is used.' },
            guard: { category: 'sensitive' },
            escalation: SENSITIVE,
          }),
        ],
      }),
    )
    renderApp({ at: '/ask' })
    const panel = await screen.findByRole('region', { name: SENSITIVE_HEADER })
    expect(screen.getByText('The sandbox budget is used.')).toBeInTheDocument()
    expect(within(panel).getByText('Dana Whitfield')).toBeInTheDocument()
    // The panel follows the message, and a saved panel is not announced.
    const message = document.querySelector('[data-slot="assistant-message"]')!
    expect(message.compareDocumentPosition(panel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(announceMock).not.toHaveBeenCalled()
  })

  it('shows it for a stopped turn too', async () => {
    signedInWith(
      conversationOut({
        turns: [
          turnOut({
            id: 't-1',
            question: 'Help',
            status: 'stopped',
            answerText: 'I am sorry',
            guard: { category: 'sensitive' },
            escalation: SENSITIVE,
          }),
        ],
      }),
    )
    renderApp({ at: '/ask' })
    expect(await screen.findByRole('region', { name: SENSITIVE_HEADER })).toBeInTheDocument()
    expect(screen.getByText('Stopped')).toBeInTheDocument()
  })

  it('shows it for a live failed turn that settles into its saved copy, without announcing again', async () => {
    const api = signedInWith(null)
    onTurn(() => {
      api.setCurrent(
        conversationOut({
          turns: [
            turnOut({
              id: 't-1',
              question: 'Help',
              status: 'failed',
              answerText: '',
              error: { code: 'budget-sandbox', message: 'The sandbox budget is used.' },
              guard: { category: 'sensitive' },
              escalation: SENSITIVE,
            }),
          ],
        }),
      )
      return eventStream(
        ['turn.started', { turnId: 't-1' }],
        ['escalation', { ...SENSITIVE, offerCase: false }],
        [
          'error',
          { code: 'budget-sandbox', message: 'The sandbox budget is used.', requestId: null },
        ],
      )
    })
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'Help{Enter}')
    await screen.findByRole('region', { name: SENSITIVE_HEADER })
    await waitFor(() => expect(useChatStore.getState().turn).toBeNull())
    expect(screen.getByRole('region', { name: SENSITIVE_HEADER })).toBeInTheDocument()
    expect(announceMock).toHaveBeenCalledTimes(1)
  })
})

describe('a panel’s arrival is announced only when it came down the stream', () => {
  it('announces a live sensitive panel once, and not again when the saved copy takes over', async () => {
    const api = signedInWith(null)
    onTurn(() => {
      api.setCurrent(
        conversationOut({
          turns: [
            turnOut({
              id: 't-1',
              question: 'Help',
              answerText: 'I’m sorry.',
              escalation: SENSITIVE,
              guard: { category: 'sensitive' },
            }),
          ],
        }),
      )
      return eventStream(
        ['turn.started', { turnId: 't-1' }],
        ['text.delta', { text: 'I’m sorry.' }],
        ['escalation', { ...SENSITIVE, offerCase: false }],
        [
          'turn.completed',
          { turnId: 't-1', servedBy: 'anthropic', usage: { inputTokens: 1, outputTokens: 1 } },
        ],
      )
    })
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'Help{Enter}')
    await screen.findByRole('region', { name: SENSITIVE_HEADER })
    // The saved copy replaces the live turn.
    await waitFor(() => expect(useChatStore.getState().turn).toBeNull())
    expect(screen.getByRole('region', { name: SENSITIVE_HEADER })).toBeInTheDocument()
    expect(announceMock).toHaveBeenCalledExactlyOnceWith(SENSITIVE_HEADER, 'polite')
  })

  it('announces nothing for a panel loaded from the server', async () => {
    signedInWith(
      conversationOut({
        turns: [
          turnOut({
            id: 't-1',
            answerText: 'I’m sorry.',
            escalation: SENSITIVE,
            guard: { category: 'sensitive' },
          }),
        ],
      }),
    )
    renderApp({ at: '/ask' })
    await screen.findByRole('region', { name: SENSITIVE_HEADER })
    expect(announceMock).not.toHaveBeenCalled()
  })

  it.each([
    ['crisis', 'crisis', 'Reach a person right now', 'Call or text 988.'],
    ['unavailable', 'guard_unavailable', 'Can’t answer right now', 'We can’t answer right now.'],
  ] as const)('announces nothing for a saved %s panel', async (kind, status, header, message) => {
    signedInWith(
      conversationOut({
        turns: [
          turnOut({
            id: 't-1',
            status,
            answerText: '',
            guard: null,
            escalation: { kind, message, hrContact: [DANA], offerCase: false },
          }),
        ],
      }),
    )
    renderApp({ at: '/ask' })
    await screen.findByRole('region', { name: header.replace('’', "'") })
    expect(announceMock).not.toHaveBeenCalled()
  })

  it('announces a second sensitive turn’s panel too: each turn has its own panel', async () => {
    const api = signedInWith(null)
    const turns: TurnOut[] = []
    let n = 0
    onTurn((question) => {
      const id = `t-${++n}`
      turns.push(
        turnOut({
          id,
          question,
          answerText: 'I’m sorry.',
          escalation: SENSITIVE,
          guard: { category: 'sensitive' },
        }),
      )
      api.setCurrent(conversationOut({ turns: [...turns] }))
      return eventStream(
        ['turn.started', { turnId: id }],
        ['text.delta', { text: 'I’m sorry.' }],
        ['escalation', { ...SENSITIVE, offerCase: false }],
        [
          'turn.completed',
          { turnId: id, servedBy: 'anthropic', usage: { inputTokens: 1, outputTokens: 1 } },
        ],
      )
    })
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'First{Enter}')
    await waitFor(() => expect(useChatStore.getState().turn).toBeNull())
    expect(announceMock).toHaveBeenCalledTimes(1)
    await user.type(await composer(), 'Second{Enter}')
    await waitFor(() => expect(announceMock).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(useChatStore.getState().turn).toBeNull())
    expect(screen.getAllByRole('region', { name: SENSITIVE_HEADER })).toHaveLength(2)
    expect(announceMock).toHaveBeenCalledTimes(2)
  })
})

describe('a new turn’s panel is a new panel, even before the last turn’s saved copy arrives', () => {
  it('announces the second sensitive turn’s panel while the first is still the live one', async () => {
    signedInWith(null)
    let n = 0
    onTurn(() => {
      const id = `t-${++n}`
      return eventStream(
        ['turn.started', { turnId: id }],
        ['text.delta', { text: 'I’m sorry.' }],
        ['escalation', { ...SENSITIVE, offerCase: false }],
        [
          'turn.completed',
          { turnId: id, servedBy: 'anthropic', usage: { inputTokens: 1, outputTokens: 1 } },
        ],
      )
    })
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'First{Enter}')
    await screen.findByRole('region', { name: SENSITIVE_HEADER })
    await waitFor(() => expect(announceMock).toHaveBeenCalledTimes(1))
    // The fake API never saves the turn, so it stays the live one when the next question goes.
    expect(useChatStore.getState().turn?.turnId).toBe('t-1')
    await user.type(await composer(), 'Second{Enter}')
    await waitFor(() => expect(useChatStore.getState().turn?.turnId).toBe('t-2'))
    await waitFor(() => expect(announceMock).toHaveBeenCalledTimes(2))
  })
})

describe('a turn that is streaming, stopped, or has failed', () => {
  it('shows Stop only while the answer streams', async () => {
    signedInWith(conversationOut({ turns: [cited()] }))
    const stream = openStream()
    onTurn(() => stream.response())
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'More{Enter}')
    // The question is on its way: Ask is busy, and there is nothing to stop yet.
    await waitFor(() => expect(useChatStore.getState().status).toBe('sending'))
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument()
    stream.push('turn.started', { turnId: 't-9' })
    stream.push('text.delta', { text: 'Working' })
    expect(await screen.findByRole('button', { name: 'Stop' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ask' })).not.toBeInTheDocument()
    stream.push('turn.completed', {
      turnId: 't-9',
      servedBy: 'anthropic',
      usage: { inputTokens: 1, outputTokens: 1 },
    })
    stream.close()
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument(),
    )
    expect(screen.getByRole('button', { name: 'Ask' })).toBeInTheDocument()
  })

  it('shows the streaming status steps, the text, and no chips or feedback until it finishes', async () => {
    signedInWith(null)
    const stream = openStream()
    onTurn(() => stream.response())
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'Sick days?{Enter}')
    stream.push('turn.started', { turnId: 't-9' })
    stream.push('status', { text: 'Searching the handbook…' })
    expect(await screen.findByText('Searching the handbook…')).toBeInTheDocument()
    stream.push('text.delta', { text: 'You get 40 hours.' })
    stream.push('citation', CA)
    expect(
      await screen.findByRole('button', { name: /Source 1: Handbook CA-4.3/ }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Sources' })).not.toBeInTheDocument()
    expect(screen.queryByText('Was this right?')).not.toBeInTheDocument()
    stream.close()
  })

  it('shows a stopped live answer with Ask again, and sends its question again', async () => {
    signedInWith(null)
    const stream = openStream()
    const posted = onTurn(() => stream.response())
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'Sick days?{Enter}')
    stream.push('turn.started', { turnId: 't-9' })
    stream.push('text.delta', { text: 'You get' })
    await user.click(await screen.findByRole('button', { name: 'Stop' }))
    expect(await screen.findByText('Stopped')).toBeInTheDocument()
    expect(screen.getByText(/You get/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Ask again' }))
    await waitFor(() => expect(posted).toHaveLength(2))
    expect(posted[1]?.question).toBe('Sick days?')
  })

  it('shows the API’s error text in the message, with Retry that sends the question again', async () => {
    signedInWith(null)
    let calls = 0
    const posted = onTurn(() =>
      ++calls === 1
        ? eventStream(
            ['turn.started', { turnId: 't-1' }],
            ['text.delta', { text: 'You get' }],
            [
              'error',
              {
                code: 'internal',
                message: 'Something went wrong partway through.',
                requestId: null,
              },
            ],
          )
        : eventStream(...completedEvents('t-2', 'You get 40 hours.')),
    )
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'Sick days?{Enter}')
    expect(await screen.findByText('Something went wrong partway through.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(posted).toHaveLength(2))
    expect(posted[1]?.question).toBe('Sick days?')
  })

  it('shows a saved failed turn with the API’s message and Retry', async () => {
    signedInWith(
      conversationOut({
        turns: [
          turnOut({
            id: 't-1',
            question: 'Sick days?',
            status: 'failed',
            answerText: '',
            error: { code: 'internal', message: 'Something went wrong on our end.' },
          }),
        ],
      }),
    )
    const posted = onTurn(() => eventStream(...completedEvents('t-2', 'Done.')))
    const { user } = renderApp({ at: '/ask' })
    expect(await screen.findByText('Something went wrong on our end.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(posted[0]?.question).toBe('Sick days?'))
  })

  it('leaves what was typed in the box when Retry re-sends the question, even if it is the same words', async () => {
    signedInWith(
      conversationOut({
        turns: [
          turnOut({
            id: 't-1',
            question: 'Sick days?',
            status: 'failed',
            answerText: '',
            error: { code: 'internal', message: 'Something went wrong on our end.' },
          }),
        ],
      }),
    )
    const posted = onTurn(() => eventStream(...completedEvents('t-2', 'Done.')))
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'Sick days?')
    await user.click(await screen.findByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(posted).toHaveLength(1))
    await screen.findByText('Done.')
    expect(await composer()).toHaveValue('Sick days?')
  })

  it('shows no Retry when a budget banner has turned the composer off', async () => {
    signedInWith(
      conversationOut({
        budget: {
          sandboxReached: false,
          dailyReached: true,
          sandboxRemainingCents: 0,
          banner: { kind: 'daily', message: 'Today’s demo budget is reached.' },
        },
        turns: [
          turnOut({
            id: 't-1',
            status: 'failed',
            answerText: '',
            error: { code: 'budget-daily', message: 'Today’s demo budget is reached.' },
          }),
        ],
      }),
    )
    renderApp({ at: '/ask' })
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
  })

  it('shows no Ask again or Try again when a budget banner has turned the composer off', async () => {
    signedInWith(
      conversationOut({
        budget: {
          sandboxReached: false,
          dailyReached: true,
          sandboxRemainingCents: 0,
          banner: { kind: 'daily', message: 'Today’s demo budget is reached.' },
        },
        turns: [
          turnOut({ id: 't-1', question: 'One?', status: 'stopped', answerText: 'Un' }),
          turnOut({
            id: 't-2',
            question: 'Two?',
            status: 'guard_unavailable',
            answerText: '',
            guard: null,
            escalation: {
              kind: 'unavailable',
              message: 'We can’t answer right now.',
              hrContact: [DANA],
              offerCase: false,
            },
          }),
        ],
      }),
    )
    renderApp({ at: '/ask' })
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    expect(screen.getByText('Stopped')).toBeInTheDocument()
    expect(screen.getByText('We can’t answer right now.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ask again' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })

  it('shows an incomplete answer with its note and its feedback', async () => {
    signedInWith(conversationOut({ turns: [cited({ incomplete: true })] }))
    renderApp({ at: '/ask' })
    expect(
      await screen.findByText('This answer was cut off before it finished.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Was this right?')).toBeInTheDocument()
  })
})

describe('a new question while the stopped answer waits for its saved copy', () => {
  async function stoppedAnswer() {
    signedInWith(null)
    const first = openStream()
    let calls = 0
    const posted = onTurn((question) => {
      calls++
      if (calls === 1) return first.response()
      return question === 'busy'
        ? problemResponse(409, 'turn-running', 'running')
        : eventStream(...completedEvents('t-2', 'Next answer.'))
    })
    const view = renderApp({ at: '/ask' })
    await view.user.type(await composer(), 'Sick days?{Enter}')
    first.push('turn.started', { turnId: 't-1' })
    first.push('text.delta', { text: 'You get half' })
    await screen.findByText(/You get half/)
    await view.user.click(await screen.findByRole('button', { name: 'Stop' }))
    await screen.findByText('Stopped')
    return { ...view, posted }
  }

  it('keeps the stopped answer on the page, before the new question and its answer', async () => {
    const { user } = await stoppedAnswer()
    await user.type(await composer(), 'And carry-over?{Enter}')
    expect(await screen.findByText('Next answer.')).toBeInTheDocument()
    // Still there, and still marked stopped, though no saved copy has arrived.
    expect(screen.getByText(/You get half/)).toBeInTheDocument()
    expect(screen.getByText('Stopped')).toBeInTheDocument()
    const questions = [...document.querySelectorAll('[data-slot="user-message"]')].map(
      (el) => el.textContent,
    )
    expect(questions).toEqual(['You asked: Sick days?', 'You asked: And carry-over?'])
  })

  it('leaves the stopped answer and the draft when the follow-up is refused (409 turn-running)', async () => {
    const { user } = await stoppedAnswer()
    await user.type(await composer(), 'busy{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent(TEXTS.stillAnswering)
    expect(screen.getByText(/You get half/)).toBeInTheDocument()
    expect(screen.getByText('Stopped')).toBeInTheDocument()
    expect(await composer()).toHaveValue('busy')
    // Nothing of the refused question joined the thread.
    expect(document.querySelectorAll('[data-slot="user-message"]')).toHaveLength(1)
  })
})

describe('feedback', () => {
  it('posts Yes and shows the thank-you line', async () => {
    signedInWith(conversationOut({ turns: [cited({ id: 't-1' })] }))
    const posted = onFeedback((body, turnId) =>
      HttpResponse.json({ turnId, ...body }, { status: 201 }),
    )
    const { user } = renderApp({ at: '/ask' })
    await user.click(await screen.findByRole('button', { name: 'Yes' }))
    expect(await screen.findByText(thanks)).toBeInTheDocument()
    expect(posted).toEqual([{ turnId: 't-1', helpful: true }])
  })

  it('posts No with the reason', async () => {
    signedInWith(conversationOut({ turns: [cited({ id: 't-1' })] }))
    const posted = onFeedback((body, turnId) =>
      HttpResponse.json({ turnId, ...body }, { status: 201 }),
    )
    const { user } = renderApp({ at: '/ask' })
    await user.click(await screen.findByRole('button', { name: 'No' }))
    await user.type(
      screen.getByRole('textbox', { name: /What was wrong/ }),
      'It cited the wrong state',
    )
    await user.click(screen.getByRole('button', { name: 'Send feedback' }))
    expect(await screen.findByText(thanks)).toBeInTheDocument()
    expect(posted).toEqual([{ turnId: 't-1', helpful: false, reason: 'It cited the wrong state' }])
  })

  it('shows the thank-you for a turn the server already has feedback for', async () => {
    signedInWith(conversationOut({ turns: [cited({ feedback: { helpful: true } })] }))
    renderApp({ at: '/ask' })
    expect(await screen.findByText(thanks)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Yes' })).not.toBeInTheDocument()
  })

  it('shows the API’s personal-data text for a reason that has a number in it, and keeps what was typed', async () => {
    signedInWith(conversationOut({ turns: [cited({ id: 't-1' })] }))
    onFeedback(() => problemResponse(422, 'personal-data', 'A different sentence.'))
    const { user } = renderApp({ at: '/ask' })
    await user.click(await screen.findByRole('button', { name: 'No' }))
    const box = screen.getByRole('textbox', { name: /What was wrong/ })
    await user.type(box, 'My SSN is 123-45-6789')
    await user.click(screen.getByRole('button', { name: 'Send feedback' }))
    const alert = await screen.findByText(TEXTS.personalData)
    expect(alert).toBeInTheDocument()
    expect(screen.queryByText('A different sentence.')).not.toBeInTheDocument()
    expect(box).toHaveValue('My SSN is 123-45-6789')
    expect(screen.queryByText(thanks)).not.toBeInTheDocument()
  })

  it('shows a failed send as an error and lets the person try again', async () => {
    signedInWith(conversationOut({ turns: [cited({ id: 't-1' })] }))
    let calls = 0
    onFeedback((body, turnId) =>
      ++calls === 1
        ? new HttpResponse(null, { status: 500 })
        : HttpResponse.json({ turnId, ...body }, { status: 201 }),
    )
    const { user } = renderApp({ at: '/ask' })
    await user.click(await screen.findByRole('button', { name: 'Yes' }))
    expect(await screen.findByText('Something went wrong sending that.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Yes' }))
    expect(await screen.findByText(thanks)).toBeInTheDocument()
  })

  it('shows the thank-you when the API says the turn already has feedback (409)', async () => {
    signedInWith(conversationOut({ turns: [cited({ id: 't-1' })] }))
    onFeedback(() => problemResponse(409, 'feedback-given', 'You already answered this.'))
    const { user } = renderApp({ at: '/ask' })
    await user.click(await screen.findByRole('button', { name: 'Yes' }))
    expect(await screen.findByText(thanks)).toBeInTheDocument()
  })

  it('keeps each turn’s feedback to itself', async () => {
    signedInWith(
      conversationOut({
        turns: [cited({ id: 't-1' }), cited({ id: 't-2', question: 'Another?' })],
      }),
    )
    onFeedback((body, turnId) => HttpResponse.json({ turnId, ...body }, { status: 201 }))
    const { user } = renderApp({ at: '/ask' })
    const yes = await screen.findAllByRole('button', { name: 'Yes' })
    await user.click(yes[0]!)
    await screen.findByText(thanks)
    expect(screen.getAllByRole('button', { name: 'Yes' })).toHaveLength(1)
  })
})

describe('the budget', () => {
  const sandboxBanner = {
    sandboxReached: true,
    dailyReached: false,
    sandboxRemainingCents: 0,
    banner: { kind: 'sandbox' as const, message: 'This sandbox has used its assistant budget.' },
  }

  it('shows the sandbox banner with its action, and turns the composer off', async () => {
    signedInWith(conversationOut({ turns: [cited()], budget: sandboxBanner }))
    renderApp({ at: '/ask' })
    expect(
      await screen.findByText('This sandbox has used its assistant budget.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start a new sandbox' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Ask Open Door' })).toBeDisabled()
    expect(screen.getByRole('textbox', { name: 'Ask Open Door' })).toHaveAttribute(
      'placeholder',
      'The assistant isn’t available in this sandbox.'.replace('’', "'"),
    )
    // The banner spans the sheet: it sits above the main content, in the shell's own slot.
    const slot = document.querySelector('[data-slot="shell-banner-slot"]')!
    expect(slot).toContainElement(screen.getByRole('button', { name: 'Start a new sandbox' }))
  })

  it('shows the daily banner with no action, and the composer off', async () => {
    signedInWith(
      conversationOut({
        turns: [cited()],
        budget: {
          sandboxReached: false,
          dailyReached: true,
          sandboxRemainingCents: 100,
          banner: { kind: 'daily', message: 'Today’s demo budget is reached.' },
        },
      }),
    )
    renderApp({ at: '/ask' })
    expect(await screen.findByText('Today’s demo budget is reached.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start a new sandbox' })).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Ask Open Door' })).toBeDisabled()
  })

  it('shows no banner and an enabled composer without one', async () => {
    signedInWith(conversationOut({ turns: [cited()] }))
    renderApp({ at: '/ask' })
    expect(await composer()).toBeEnabled()
    expect(document.querySelector('[data-slot="shell-banner-slot"]')).toBeEmptyDOMElement()
  })

  it('also shows the banner on the home of an empty conversation', async () => {
    signedInWith(conversationOut({ budget: sandboxBanner }))
    renderApp({ at: '/ask' })
    expect(
      await screen.findByText('This sandbox has used its assistant budget.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Ask Open Door' })).toBeDisabled()
  })

  it('starts a new sandbox as the same persona, from the banner', async () => {
    signedInWith(conversationOut({ turns: [cited()], budget: sandboxBanner }))
    const created: unknown[] = []
    server.use(
      http.post(`${window.location.origin}/api/v1/sandboxes`, async ({ request }) => {
        created.push(await request.json())
        return new HttpResponse(null, { status: 500 })
      }),
    )
    const { user } = renderApp({ at: '/ask' })
    await user.click(await screen.findByRole('button', { name: 'Start a new sandbox' }))
    await waitFor(() => expect(created).toEqual([{ persona: 'priya' }]))
    expect(await screen.findByText("We couldn't start a sandbox.")).toBeInTheDocument()
  })

  it('takes the banner from a send the API refused with a budget problem, and says it once', async () => {
    const api = signedInWith(conversationOut({ turns: [cited()] }))
    onTurn(() => {
      api.setCurrent(conversationOut({ turns: [cited()], budget: sandboxBanner }))
      return problemResponse(429, 'budget-sandbox', 'This sandbox has used its assistant budget.')
    })
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'More{Enter}')
    expect(await screen.findByRole('button', { name: 'Start a new sandbox' })).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByRole('textbox', { name: 'Ask Open Door' })).toBeDisabled(),
    )
    // The banner is the one message: the composer's own line (the budget stop) wins over the send
    // error, so nothing under the box repeats it.
    expect(screen.getAllByText('This sandbox has used its assistant budget.')).toHaveLength(1)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows the 429’s own words under the box when the conversation read has no banner (a long question the smallest one would not have been refused for)', async () => {
    signedInWith(conversationOut({ turns: [cited()] }))
    onTurn(() =>
      problemResponse(429, 'budget-sandbox', 'There is not room for a question that long.'),
    )
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'A very long question{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'There is not room for a question that long.',
    )
    // No banner came with the refetch, so the composer stays on and the draft is kept.
    expect(screen.queryByRole('button', { name: 'Start a new sandbox' })).not.toBeInTheDocument()
    expect(await composer()).toBeEnabled()
    expect(await composer()).toHaveValue('A very long question')
  })

  it('shows the daily banner and a disabled composer before the first conversation, from the budget route', async () => {
    installFakeApi('priya')
    installAssistantApi({
      budget: {
        sandboxReached: false,
        dailyReached: true,
        sandboxRemainingCents: 100,
        banner: { kind: 'daily', message: 'Today’s demo budget is reached.' },
      },
    })
    renderApp({ at: '/ask' })
    expect(await screen.findByText('Today’s demo budget is reached.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Ask Open Door' })).toBeDisabled()
  })

  it('waits for the budget before it shows the composer of a person with no conversation', async () => {
    installFakeApi('priya')
    installAssistantApi()
    let release!: () => void
    const held = new Promise<void>((resolve) => {
      release = resolve
    })
    server.use(
      http.get(`${window.location.origin}/api/v1/assistant/budget`, async () => {
        await held
        return HttpResponse.json({
          sandboxReached: false,
          dailyReached: true,
          sandboxRemainingCents: 0,
          banner: { kind: 'daily', message: 'Today’s demo budget is reached.' },
        })
      }),
    )
    renderApp({ at: '/ask' })
    await screen.findByRole('link', { name: /Handbook updated/ })
    expect(screen.queryByRole('textbox', { name: 'Ask Open Door' })).not.toBeInTheDocument()
    release()
    // Never an enabled composer first.
    expect(await screen.findByRole('textbox', { name: 'Ask Open Door' })).toBeDisabled()
  })

  it('does not read the budget route when there is a conversation: it carries its own', async () => {
    installFakeApi('priya')
    const api = installAssistantApi({ conversation: conversationOut({ turns: [cited()] }) })
    renderApp({ at: '/ask' })
    await screen.findByText(/You get 40 hours/)
    expect(api.requests.budget).toBe(0)
  })

  it('shows the budget text once when the first question is refused at the cap', async () => {
    installFakeApi('priya')
    const api = installAssistantApi()
    const daily = {
      sandboxReached: false,
      dailyReached: true,
      sandboxRemainingCents: 0,
      banner: { kind: 'daily' as const, message: 'Today’s demo budget is reached.' },
    }
    // The person had room when the page loaded; the day's cap was reached since.
    onTurn(() => {
      api.setCurrent(conversationOut({ budget: daily }))
      return problemResponse(429, 'budget-daily', 'Today’s demo budget is reached.')
    })
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'First question{Enter}')
    expect(await screen.findByText('Today’s demo budget is reached.')).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByRole('textbox', { name: 'Ask Open Door' })).toBeDisabled(),
    )
    expect(screen.getAllByText('Today’s demo budget is reached.')).toHaveLength(1)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    // The draft stays for when the budget is back.
    expect(screen.getByRole('textbox', { name: 'Ask Open Door' })).toHaveValue('First question')
  })
})

describe('the composer', () => {
  it('shows the personal-data warning in the API’s words and sends nothing', async () => {
    signedInWith(conversationOut({ turns: [cited()] }))
    const posted = onTurn(() => eventStream())
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'My SSN is 123-45-6789{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent(TEXTS.personalData)
    expect(posted).toHaveLength(0)
  })

  it('says the API’s "still answering" when Enter is pressed while an answer streams', async () => {
    signedInWith(conversationOut({ turns: [cited()] }))
    const stream = openStream()
    onTurn(() => stream.response())
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'First{Enter}')
    stream.push('turn.started', { turnId: TURN_ID })
    stream.push('text.delta', { text: 'Working' })
    await screen.findByRole('button', { name: 'Stop' })
    await user.type(await composer(), 'Second{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent(TEXTS.stillAnswering)
    stream.close()
  })

  it('shows a failed send under the box, keeps the question, and Ask sends it again', async () => {
    signedInWith(conversationOut({ turns: [cited()] }))
    let calls = 0
    const posted = onTurn(() =>
      ++calls === 1
        ? new Response(null, { status: 500 })
        : eventStream(...completedEvents('t-2', 'Back.')),
    )
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'More{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong sending that.')
    // One failed-send line, and no Retry button of its own: Ask is the retry.
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
    expect(await composer()).toHaveValue('More')
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    await waitFor(() => expect(posted).toHaveLength(2))
  })
})

describe('the header and the shell around it', () => {
  it('draws one sandbox pill in the header at every width, and the shell’s own step aside', async () => {
    signedInWith(conversationOut({ turns: [cited()] }))
    renderApp({ at: '/ask' })
    await screen.findByRole('button', { name: 'Start a new conversation' })
    const pills = [...document.querySelectorAll('[data-slot="sandbox-indicator"]')]
    const header = pills.filter((pill) => pill.closest('[data-slot="conversation-header"]'))
    expect(header).toHaveLength(1)
    expect(header[0]).not.toHaveClass('max-[760px]:hidden')
    // The top bar's pill is hidden below 760 px, and the rail has none.
    const others = pills.filter((pill) => !pill.closest('[data-slot="conversation-header"]'))
    expect(others).toHaveLength(1)
    expect(others[0]).toHaveClass('max-[760px]:hidden')
    expect(screen.getByRole('complementary', { name: 'Sandbox status' })).not.toContainElement(
      others[0] as HTMLElement,
    )
    // The sheet clips instead of hiding, so the header and the composer can stick to the window.
    expect(document.querySelector('[data-slot="shell-sheet"]')).toHaveClass('overflow-clip')
  })

  it('keeps the shell’s pills on the home', async () => {
    signedInWith(null)
    renderApp({ at: '/ask' })
    await composer()
    const pills = document.querySelectorAll('[data-slot="sandbox-indicator"]')
    expect(pills).toHaveLength(2)
    expect(document.querySelector('[data-slot="conversation-header"]')).toBeNull()
    expect(document.querySelector('[data-slot="shell-sheet"]')).toHaveClass('overflow-hidden')
  })

  it('puts the header row 8 px higher at desktop width, where the design draws it', async () => {
    signedInWith(conversationOut({ turns: [cited()] }))
    renderApp({ at: '/ask' })
    await screen.findByRole('button', { name: 'Start a new conversation' })
    const row = document.querySelector('[data-slot="conversation-header"]')!.parentElement!
    // 8 px less above the row than it had (pt-7 became pt-5), moved to below it (pb-4 became
    // pb-6), so the row sits at about 49 px (the design's) and the first message stays put.
    expect(row).toHaveClass('pt-5', 'pb-6')
    expect(row).not.toHaveClass('pt-7')
    // Phones keep their own, tighter, spacing.
    expect(row).toHaveClass('max-[760px]:pt-4', 'max-[760px]:pb-4')
  })

  it('puts the retention line under the composer below 640 px, and in the header above it', async () => {
    signedInWith(conversationOut({ turns: [cited()] }))
    renderApp({ at: '/ask' })
    await screen.findByRole('button', { name: 'Start a new conversation' })
    const lines = document.querySelectorAll('[data-slot="retention-line"]')
    expect(lines).toHaveLength(2)
    const [inHeader, underComposer] = [...lines]
    expect(inHeader?.closest('[data-slot="conversation-header"]')).not.toBeNull()
    expect(underComposer).toHaveClass('sm:hidden')
  })

  it('does not hide the rail’s glance on other pages’ shells', async () => {
    signedInWith(null)
    renderApp({ at: '/ask' })
    await composer()
    const rail = screen.getByRole('complementary', { name: 'Sandbox status' })
    expect(rail).not.toHaveClass('max-[760px]:hidden')
  })
})

describe('the conversation’s reading order', () => {
  it('puts the marker, then the chips, then Yes, No, and Show your work, in the thread', async () => {
    signedInWith(conversationOut({ turns: [cited()] }))
    const { user } = renderApp({ at: '/ask' })
    await screen.findByRole('button', { name: 'Start a new conversation' })
    const names: string[] = []
    for (let i = 0; i < 20; i++) {
      await user.tab()
      const el = document.activeElement as HTMLElement
      names.push(el.getAttribute('aria-label') ?? el.textContent ?? '')
    }
    const start = names.indexOf('Start a new conversation')
    expect(start).toBeGreaterThan(-1)
    expect(names.slice(start, start + 9)).toEqual([
      'Start a new conversation',
      'Source 1: Handbook CA-4.3, California addendum',
      'Source 2: Handbook §4.3, Time off',
      'Source 1: Handbook CA-4.3, California addendum',
      'Source 2: Handbook §4.3, Time off',
      'Yes',
      'No',
      'Show your work',
      'Ask Open Door',
    ])
  })
})

describe('the shell gives its pills back when the conversation goes', () => {
  it('shows the rail’s pill again after "Start a new conversation"', async () => {
    signedInWith(conversationOut({ turns: [cited()] }))
    const { user } = renderApp({ at: '/ask' })
    await user.click(await screen.findByRole('button', { name: 'Start a new conversation' }))
    await screen.findByRole('heading', { level: 1 })
    const rail = screen.getByRole('complementary', { name: 'Sandbox status' })
    expect(within(rail).getByText(/Sandbox resets in/)).toBeInTheDocument()
    expect(document.querySelector('[data-slot="conversation-header"]')).toBeNull()
  })
})

describe('following the thread', () => {
  // jsdom has no layout, so the two things "at the bottom" reads are stood in for: where the end of
  // the thread is (the sentinel's bottom edge), and how tall the sticky composer is.
  const COMPOSER_PX = 186
  const WINDOW_PX = 768
  let scrollIntoView: ReturnType<typeof vi.spyOn>
  let threadEnd = 0
  let marginAtCall: string[] = []

  beforeEach(() => {
    threadEnd = 0
    marginAtCall = []
    scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(function (
      this: Element,
    ) {
      marginAtCall.push((this as HTMLElement).style.scrollMarginBottom)
      return Promise.resolve() as unknown as undefined
    })
    const original = Element.prototype.getBoundingClientRect
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (
      this: Element,
    ) {
      const rect = original.call(this)
      return this.getAttribute('data-slot') === 'thread-end'
        ? ({ ...rect, bottom: threadEnd } as DOMRect)
        : rect
    })
    vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockImplementation(function (
      this: HTMLElement,
    ) {
      return this.getAttribute('data-slot') === 'composer-dock' ? COMPOSER_PX : 0
    })
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  /** The end of the thread this far below (+) or above (-) the top edge of the sticky composer. */
  const endBelowComposerTop = (px: number) => {
    threadEnd = WINDOW_PX - COMPOSER_PX + px
  }
  /** The reader scrolls: the page's own scroll event, with the thread end where it now is. */
  const readerScrollsTo = (px: number) => {
    endBelowComposerTop(px)
    act(() => {
      window.dispatchEvent(new Event('scroll'))
    })
  }
  /** The page grows under the reader (a long chunk of text, a wrapped step): no scroll event. */
  const pageGrowsBy = (px: number) => {
    threadEnd += px
  }

  it('shows the latest turn when the page opens', async () => {
    signedInWith(conversationOut({ turns: [cited()] }))
    renderApp({ at: '/ask' })
    await screen.findByText(/You get 40 hours/)
    expect(scrollIntoView).toHaveBeenCalled()
  })

  it('scrolls the end of the thread above the sticky composer, by the composer’s height', async () => {
    signedInWith(conversationOut({ turns: [cited()] }))
    renderApp({ at: '/ask' })
    await screen.findByText(/You get 40 hours/)
    expect(marginAtCall.at(-1)).toBe(`${COMPOSER_PX}px`)
  })

  it('scrolls to the new question when one is sent', async () => {
    signedInWith(conversationOut({ turns: [cited()] }))
    const stream = openStream()
    onTurn(() => stream.response())
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'More{Enter}')
    await waitFor(() => expect(useChatStore.getState().status).toBe('sending'))
    // From the moment of the send: the call came with the question, before any answer arrived.
    expect(scrollIntoView).toHaveBeenCalledTimes(2)
    stream.close()
  })

  async function finishLiveTurn(readerPx: number) {
    const api = signedInWith(conversationOut({ turns: [cited()] }))
    const stream = openStream()
    onTurn(() => stream.response())
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'More{Enter}')
    stream.push('turn.started', { turnId: 't-9' })
    stream.push('text.delta', { text: 'Working' })
    await screen.findByText(/Working/)
    // Where the reader is while the answer settles (sending the question took them to the end).
    readerScrollsTo(readerPx)
    // The server now holds the finished turn, and the stream reports it done.
    api.setCurrent(
      conversationOut({
        turns: [cited(), turnOut({ id: 't-9', question: 'More', answerText: 'Working' })],
      }),
    )
    scrollIntoView.mockClear()
    stream.push('turn.completed', {
      turnId: 't-9',
      servedBy: 'anthropic',
      usage: { inputTokens: 1, outputTokens: 1 },
    })
    stream.close()
    await waitFor(() => expect(useChatStore.getState().turn).toBeNull())
    expect(screen.getAllByText('Was this right?')).toHaveLength(2)
  }

  it('keeps following when the live turn settles into its saved copy, which adds the chips and feedback', async () => {
    await finishLiveTurn(-20)
    expect(scrollIntoView).toHaveBeenCalled()
  })

  it('leaves a reader who scrolled up alone when the live turn settles', async () => {
    await finishLiveTurn(600)
    expect(scrollIntoView).not.toHaveBeenCalled()
  })

  it('counts the sticky composer: a reader who scrolls to where the end is hidden under it by more than 160 px stops following', async () => {
    signedInWith(conversationOut({ turns: [cited()] }))
    const stream = openStream()
    onTurn(() => stream.response())
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'More{Enter}')
    stream.push('turn.started', { turnId: 't-9' })
    stream.push('text.delta', { text: 'One ' })
    await screen.findByText(/One/)
    // Measured from the window's bottom edge the end is on screen (782 vs 768 is 14 px under it),
    // but 200 px below where the composer starts, so the reader is not at the bottom.
    readerScrollsTo(200)
    scrollIntoView.mockClear()
    stream.push('text.delta', { text: 'two' })
    await screen.findByText(/One two/)
    expect(scrollIntoView).not.toHaveBeenCalled()
    // Back within 160 px of the composer's edge, they follow again.
    readerScrollsTo(100)
    stream.push('text.delta', { text: ' three' })
    await screen.findByText(/One two three/)
    expect(scrollIntoView).toHaveBeenCalled()
    stream.close()
  })

  it('keeps following through a big growth: 400 px of new text does not take the reader off the bottom', async () => {
    signedInWith(conversationOut({ turns: [cited()] }))
    const stream = openStream()
    onTurn(() => stream.response())
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'More{Enter}')
    stream.push('turn.started', { turnId: 't-9' })
    stream.push('text.delta', { text: 'One ' })
    await screen.findByText(/One/)
    readerScrollsTo(-20)
    // A long chunk lays out 400 px below where the end was: the reader did not move.
    pageGrowsBy(400)
    scrollIntoView.mockClear()
    stream.push('text.delta', { text: 'a very long chunk' })
    await screen.findByText(/a very long chunk/)
    expect(scrollIntoView).toHaveBeenCalled()
    // And the next piece, laid out another 400 px down, is followed too.
    pageGrowsBy(400)
    scrollIntoView.mockClear()
    stream.push('text.delta', { text: ' and another' })
    await screen.findByText(/and another/)
    expect(scrollIntoView).toHaveBeenCalled()
    stream.close()
  })

  it('follows a growing answer while the reader is at the bottom, and not once they scroll up', async () => {
    signedInWith(conversationOut({ turns: [cited()] }))
    const stream = openStream()
    onTurn(() => stream.response())
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'More{Enter}')
    stream.push('turn.started', { turnId: 't-9' })
    stream.push('text.delta', { text: 'One ' })
    await screen.findByText(/One/)
    scrollIntoView.mockClear()
    stream.push('text.delta', { text: 'two ' })
    await screen.findByText(/One two/)
    expect(scrollIntoView).toHaveBeenCalled()

    readerScrollsTo(2000)
    scrollIntoView.mockClear()
    stream.push('text.delta', { text: 'three' })
    await screen.findByText(/One two three/)
    expect(scrollIntoView).not.toHaveBeenCalled()
    stream.close()
  })

  it('leaves room under the last turn: the thread ends above the composer, not behind it', async () => {
    signedInWith(conversationOut({ turns: [cited()] }))
    renderApp({ at: '/ask' })
    await screen.findByText(/You get 40 hours/)
    const end = document.querySelector('[data-slot="thread-end"]')!
    expect(end.nextElementSibling).toBeNull()
    expect(document.querySelector('[data-slot="composer-dock"]')).not.toBeNull()
    // The composer follows the thread in the page, so the last of the page scrolls above it.
    const thread = document.querySelector('[data-slot="conversation-thread"]')!
    expect(thread.nextElementSibling).toBe(document.querySelector('[data-slot="composer-dock"]'))
  })
})

describe('with the scroll methods a real browser has', () => {
  it('mounts, updates, and unmounts the conversation without a React error, though scrollIntoView returns a Promise', async () => {
    // Chromium's scrollIntoView returns a Promise. An effect that hands it back to React as its
    // clean-up crashes the page ("destroy is not a function"); jsdom's returns nothing, so the
    // test says what a browser does.
    const scrollIntoView = vi
      .spyOn(Element.prototype, 'scrollIntoView')
      .mockImplementation(() => Promise.resolve() as unknown as undefined)
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
    const api = signedInWith(null)
    onTurn(() => {
      api.setCurrent(conversationOut({ turns: [cited({ id: 't-1', question: 'Sick days?' })] }))
      return eventStream(...completedEvents('t-1', ANSWER))
    })
    const { user, router } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'Sick days?{Enter}')
    await screen.findByText(/You get 40 hours of sick leave\./)
    await waitFor(() => expect(useChatStore.getState().turn).toBeNull())
    expect(scrollIntoView).toHaveBeenCalled()
    // Leaving the page unmounts the conversation.
    await act(async () => {
      await router.navigate('/handbook')
    })
    await waitFor(() => expect(router.state.location.pathname).toBe('/handbook'))
    expect(screen.queryByText(/Something went wrong/)).not.toBeInTheDocument()
    // (jsdom also warns about the handbook's <search> element, which is not what this is about.)
    const reported = errors.mock.calls.map((call) => String(call[0]))
    expect(reported.filter((text) => /must not return|destroy/.test(text))).toEqual([])
    errors.mockRestore()
    scrollIntoView.mockRestore()
  })
})
