import { http, HttpResponse } from 'msw'
import type {
  AssistantTextsOut,
  BudgetOut,
  ConversationOut,
  ProposalOut,
  TurnOut,
} from '@/api/generated'
import { CARD_BOOK, EXPIRES_AT } from '@/app/gallery/fixtures/timeoff'
import { californiaSickLeave, paragraph, passageView, sectionSummary } from './handbook-fixtures'
import { server } from './msw'

// A fake assistant API for the chat store, the hooks, and the pages that use them: the two fixed
// texts, the current conversation, creating one, and a turn's event stream.

const url = (path: string) => `${window.location.origin}${path}`

export const CONVERSATION_ID = 'c0ffee00-0000-4000-8000-000000000001'
export const TURN_ID = 'c0ffee00-0000-4000-8000-0000000000aa'

export const TEXTS: AssistantTextsOut = {
  personalData:
    "That looks like a Social Security or card number. Please take it out; I can't take those.",
  stillAnswering: "I'm still answering your last question.",
}

/** The budget route's answer while neither cap is reached. */
export const NO_BUDGET_STOP: BudgetOut = {
  sandboxReached: false,
  dailyReached: false,
  sandboxRemainingCents: 500,
  banner: null,
}

export function turnOut(overrides: Partial<TurnOut> = {}): TurnOut {
  return {
    id: TURN_ID,
    question: 'How many sick days do I get?',
    status: 'completed',
    answerText: 'You get 5 days.',
    citations: [],
    incomplete: false,
    error: null,
    escalation: null,
    notFound: false,
    guard: { category: 'ordinary' },
    toolCalls: [],
    sections: [],
    feedback: null,
    proposals: [],
    startedAt: '2026-10-18T10:00:00Z',
    endedAt: '2026-10-18T10:00:05Z',
    ...overrides,
  }
}

export const PROPOSAL_ID = 'c0ffee00-0000-4000-8000-0000000000b1'

/** A pending booking card, as the API sends it, with any field overridden. */
export function proposalOut(overrides: Partial<ProposalOut> = {}): ProposalOut {
  return {
    id: PROPOSAL_ID,
    action: 'timeoff.request',
    status: 'pending',
    canceledReason: null,
    expiresAt: EXPIRES_AT,
    card: CARD_BOOK,
    failure: null,
    turnRunning: false,
    deniedNote: null,
    ...overrides,
  }
}

export function conversationOut(overrides: Partial<ConversationOut> = {}): ConversationOut {
  return {
    id: CONVERSATION_ID,
    createdAt: '2026-10-18T10:00:00Z',
    turns: [],
    hrContacts: [],
    budget: {
      sandboxReached: false,
      dailyReached: false,
      sandboxRemainingCents: 500,
      banner: null,
    },
    longHistory: false,
    historyTooLong: false,
    outdated: false,
    ...overrides,
  }
}

/** One wire event, as the API writes it. */
export function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

const encoder = new TextEncoder()
const STREAM_HEADERS = { 'Content-Type': 'text/event-stream' }

/** A finished stream of events, each `[name, data]`. */
export function eventStream(...events: [event: string, data: unknown][]): Response {
  return new HttpResponse(encoder.encode(events.map(([e, d]) => sse(e, d)).join('')), {
    headers: STREAM_HEADERS,
  })
}

/** A stream the test feeds by hand, to hold a turn open. */
export function openStream() {
  let controller!: ReadableStreamDefaultController<Uint8Array>
  let closed = false
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c
    },
    cancel() {
      closed = true
    },
  })
  return {
    response: () => new HttpResponse(body, { headers: STREAM_HEADERS }),
    push(event: string, data: unknown) {
      if (!closed) controller.enqueue(encoder.encode(sse(event, data)))
    },
    close() {
      if (!closed) controller.close()
      closed = true
    },
  }
}

export function problemResponse(
  status: number,
  type: string,
  detail: string,
  requestId = 'req-1',
): Response {
  return HttpResponse.json(
    { type, title: detail, status, instance: '/x', detail },
    { status, headers: { 'X-Request-ID': requestId, 'Content-Type': 'application/problem+json' } },
  )
}

export const turnsPath = (conversationId = ':id') =>
  `/api/v1/assistant/conversations/${conversationId}/turns`

/** Answers the turn route for any conversation. Returns what was posted. */
export function onTurn(handler: (question: string, conversationId: string) => Response) {
  const posted: { conversationId: string; question: string; csrf: string | null }[] = []
  server.use(
    http.post(url(turnsPath()), async ({ request, params }) => {
      const { question } = (await request.json()) as { question: string }
      const conversationId = String(params.id)
      posted.push({ conversationId, question, csrf: request.headers.get('X-CSRF-Token') })
      return handler(question, conversationId)
    }),
  )
  return posted
}

type InstallOptions = { conversation?: ConversationOut | null; budget?: BudgetOut }

/** The texts route, the current conversation (mutable), and creating a conversation. */
export function installAssistantApi({
  conversation = null,
  budget = NO_BUDGET_STOP,
}: InstallOptions = {}) {
  let current: ConversationOut | null = conversation
  let budgetNow: BudgetOut = budget
  const requests = { texts: 0, current: 0, created: 0, budget: 0 }
  server.use(
    http.get(url('/api/v1/assistant/texts'), () => {
      requests.texts++
      return HttpResponse.json(TEXTS)
    }),
    http.get(url('/api/v1/assistant/conversations/current'), () => {
      requests.current++
      return HttpResponse.json(current)
    }),
    http.get(url('/api/v1/assistant/budget'), () => {
      requests.budget++
      return HttpResponse.json(budgetNow)
    }),
    http.post(url('/api/v1/assistant/conversations'), () => {
      requests.created++
      current = conversationOut()
      return HttpResponse.json(current, { status: 201 })
    }),
  )
  return {
    requests,
    /** What the next read of the budget route returns. */
    setBudget(next: BudgetOut) {
      budgetNow = next
    },
    /** What the next read of the current conversation returns. */
    setCurrent(next: ConversationOut | null) {
      current = next
    },
  }
}

/**
 * Serves the handbook's passage route for any section and passage, for the source panel. The
 * passage's text names the section and passage it was asked for. Returns the requests, in order.
 */
export function installPassages({ failing = false }: { failing?: boolean } = {}) {
  const requests: { sectionId: string; passageId: string }[] = []
  let failNext = failing
  server.use(
    http.get(url('/api/v1/handbook/sections/:sectionId/passages/:passageId'), ({ params }) => {
      const sectionId = decodeURIComponent(String(params.sectionId))
      const passageId = decodeURIComponent(String(params.passageId))
      requests.push({ sectionId, passageId })
      if (failNext) return new HttpResponse(null, { status: 500 })
      const section = sectionId.startsWith('CA-')
        ? californiaSickLeave({ id: sectionId })
        : sectionSummary({ id: sectionId })
      return HttpResponse.json(
        passageView({
          section,
          previous: null,
          passage: paragraph(passageId, `The ${passageId} text of ${sectionId}.`),
          next: null,
        }),
      )
    }),
  )
  return {
    requests,
    /** Make the passage route work again after it failed. */
    recover() {
      failNext = false
    },
  }
}

/** Answers feedback for any turn. Returns what was posted. */
export function onFeedback(
  handler: (body: { helpful: boolean; reason?: string | null }, turnId: string) => Response,
) {
  const posted: { turnId: string; helpful: boolean; reason?: string | null }[] = []
  server.use(
    http.post(url('/api/v1/assistant/turns/:turnId/feedback'), async ({ request, params }) => {
      const body = (await request.json()) as { helpful: boolean; reason?: string | null }
      const turnId = String(params.turnId)
      posted.push({ turnId, ...body })
      return handler(body, turnId)
    }),
  )
  return posted
}

/** Answers Confirm and Dismiss for any proposal. Returns what was posted, in order. */
export function onProposalAction(handler: (kind: 'confirm' | 'cancel', body: unknown) => Response) {
  const posted: { kind: 'confirm' | 'cancel'; proposalId: string; body: unknown }[] = []
  for (const kind of ['confirm', 'cancel'] as const) {
    server.use(
      http.post(
        url(`/api/v1/assistant/proposals/:proposalId/${kind}`),
        async ({ request, params }) => {
          const text = await request.text()
          const body: unknown = text === '' ? null : JSON.parse(text)
          posted.push({ kind, proposalId: String(params.proposalId), body })
          return handler(kind, body)
        },
      ),
    )
  }
  return posted
}
