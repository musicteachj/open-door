import { http, HttpResponse } from 'msw'
import type {
  CaseDetailOut,
  CaseSentOut,
  CaseStatusOut,
  CaseSummaryOut,
  CaseTextsOut,
  CountsOut,
  OpenCaseBody,
  QueuePageOut,
} from '@/api/generated'
import { CASE_BULLETS, SENT_LINE, WAITING_LIMIT, type DemoCase } from '@/app/gallery/fixtures/cases'
import { DANA } from './assistant-fixtures'
import { problemResponse } from './fake-assistant'
import { meFor } from './fixtures'
import { server } from './msw'

// A fake of the case routes for the page tests. It counts every call, so a test can say how many
// audited reads a view made (the summary and the words), and it answers a POST /cases as the
// server does: the same case for a repeated submission ID.

const url = (path: string) => `${window.location.origin}${path}`

export const CASE_TEXTS: CaseTextsOut = {
  bullets: CASE_BULLETS,
  replyBy: '2026-10-28',
  waitingLimit: WAITING_LIMIT,
  hrContacts: [DANA],
}

export function statusView(over: Partial<CaseStatusOut> = {}): CaseStatusOut {
  return {
    id: 'new-case',
    category: 'harassment_discrimination',
    status: 'new',
    sentAt: '2026-10-26T16:41:00Z',
    replyBy: '2026-10-28',
    statusChangedAt: '2026-10-26T16:41:00Z',
    ...over,
  }
}

export type FakeCasesOptions = {
  mine?: CaseStatusOut[]
  /** The next POST /cases answers with this problem instead of a case. */
  openProblem?: { status: number; type: string; detail: string } | null
  /** The case is saved before that problem is answered (a lost response, a conflict). */
  saveBeforeProblem?: boolean
  crisisText?: string | null
  /** The queue's pages, keyed by cursor ('' is the first page). */
  queue?: Record<string, QueuePageOut>
  details?: Record<string, CaseDetailOut>
  summaries?: Record<string, CaseSummaryOut | { problem: number }>
  words?: Record<string, string | { problem: number }>
  /** HR's counts for the nav and the rail. */
  counts?: CountsOut
}

export function installFakeCases(options: FakeCasesOptions = {}) {
  const state = {
    mine: options.mine ?? [],
    openProblem: options.openProblem ?? null,
    saveBeforeProblem: options.saveBeforeProblem ?? false,
    crisisText: options.crisisText ?? null,
  }
  const bySubmission = new Map<string, CaseSentOut>()
  const calls = {
    posts: [] as OpenCaseBody[],
    texts: 0,
    mine: 0,
    counts: 0,
    summary: [] as string[],
    text: [] as string[],
    detail: [] as string[],
    list: [] as { status: string | null; cursor: string | null }[],
    status: [] as { id: string; to: string }[],
    rewrites: [] as string[],
  }
  // What the detail's metadata says now, so a read or a change shows in the timeline.
  const details = { ...options.details }
  const summaries = { ...options.summaries }
  const wordsOf = { ...options.words }
  // The next audited read of each kind waits for its gate, so a test can hold a request open.
  const gates: { summary: Promise<void> | null; text: Promise<void> | null } = {
    summary: null,
    text: null,
  }
  function hold(kind: 'summary' | 'text') {
    let release!: () => void
    gates[kind] = new Promise<void>((resolve) => (release = resolve))
    return release
  }
  function saveCase(body: OpenCaseBody): CaseSentOut {
    const created = statusView({
      id: `case-${bySubmission.size + 1}`,
      category: body.category,
    })
    state.mine = [created, ...state.mine]
    const sent: CaseSentOut = {
      case: created,
      sentLine: SENT_LINE,
      created: true,
      crisisText: state.crisisText,
    }
    bySubmission.set(body.submissionId, sent)
    return sent
  }
  const handlers = {
    status: undefined as undefined | ((id: string, to: string) => Response | undefined),
    rewrite: undefined as undefined | ((id: string) => Response | undefined),
  }

  server.use(
    http.get(url('/api/v1/cases/texts'), () => {
      calls.texts++
      return HttpResponse.json(CASE_TEXTS)
    }),
    http.get(url('/api/v1/cases/mine'), () => {
      calls.mine++
      return HttpResponse.json({ items: state.mine })
    }),
    http.post(url('/api/v1/cases'), async ({ request }) => {
      const body = (await request.json()) as OpenCaseBody
      calls.posts.push(body)
      const earlier = bySubmission.get(body.submissionId)
      if (state.openProblem) {
        if (state.saveBeforeProblem && !earlier) saveCase(body)
        const { status, type, detail } = state.openProblem
        return problemResponse(status, type, detail)
      }
      if (earlier) return HttpResponse.json({ ...earlier, created: false }, { status: 200 })
      return HttpResponse.json(saveCase(body), { status: 201 })
    }),
    http.get(url('/api/v1/cases'), ({ request }) => {
      const params = new URL(request.url).searchParams
      calls.list.push({ status: params.get('status'), cursor: params.get('cursor') })
      const cursor = params.get('cursor')
      // A cursor the test did not define is a failed read.
      if (cursor && !options.queue?.[cursor]) return problemResponse(500, 'about:blank', 'Broke.')
      const page = options.queue?.[cursor ?? '']
      return HttpResponse.json(page ?? ({ items: [], nextCursor: null } satisfies QueuePageOut))
    }),
    http.get(url('/api/v1/cases/counts'), () => {
      calls.counts++
      return HttpResponse.json(options.counts ?? { new: 0, replyDue: 0 })
    }),
    http.get(url('/api/v1/cases/:id'), ({ params }) => {
      const id = String(params.id)
      calls.detail.push(id)
      const detail = details[id]
      return detail ? HttpResponse.json(detail) : problemResponse(404, 'case-not-found', 'No case')
    }),
    http.get(url('/api/v1/cases/:id/summary'), async ({ params }) => {
      const id = String(params.id)
      calls.summary.push(id)
      const answer = summaries[id]
      const gate = gates.summary
      gates.summary = null
      await gate
      if (answer && 'problem' in answer) return problemResponse(answer.problem, 'x', 'failed')
      return HttpResponse.json(answer ?? { status: 'none' })
    }),
    http.get(url('/api/v1/cases/:id/text'), async ({ params }) => {
      const id = String(params.id)
      calls.text.push(id)
      const answer = wordsOf[id]
      const gate = gates.text
      gates.text = null
      await gate
      if (answer && typeof answer === 'object')
        return problemResponse(answer.problem, 'x', 'failed')
      // Opening the words adds a `text_read` row to the timeline, as the server does.
      const detail = details[id]
      if (detail?.timeline) {
        details[id] = {
          ...detail,
          timeline: [
            ...detail.timeline,
            {
              kind: 'text_read',
              occurredAt: '2026-10-26T17:00:00Z',
              actorPersonId: meFor('dana').id,
              actorGivenName: 'Dana',
              actorFamilyName: 'Whitfield',
              fromStatus: null,
              toStatus: null,
            },
          ],
        }
      }
      return HttpResponse.json({ text: answer ?? '' })
    }),
    http.post(url('/api/v1/cases/:id/status'), async ({ params, request }) => {
      const id = String(params.id)
      const { to } = (await request.json()) as { to: string }
      calls.status.push({ id, to })
      const refused = handlers.status?.(id, to)
      if (refused) return refused
      const detail = details[id]
      if (detail) details[id] = { ...detail, status: to as CaseDetailOut['status'] }
      return HttpResponse.json(statusView({ id, status: to as CaseStatusOut['status'] }))
    }),
    http.post(url('/api/v1/cases/:id/summary'), ({ params }) => {
      const id = String(params.id)
      calls.rewrites.push(id)
      return handlers.rewrite?.(id) ?? HttpResponse.json({ status: 'writing' }, { status: 202 })
    }),
  )

  return {
    calls,
    state,
    details,
    summaries,
    /** Holds the next summary or words read open until the returned function is called. */
    hold,
    /** Makes the next status changes answer as this (for a 409), or undefined for success. */
    onStatus: (fn: typeof handlers.status) => {
      handlers.status = fn
    },
    onRewrite: (fn: typeof handlers.rewrite) => {
      handlers.rewrite = fn
    },
  }
}

/**
 * The detail's metadata for one of the gallery's cases, as the API sends it to HR: no words and no
 * summary text. Another person's case has its timeline and a summary state; HR's own has neither.
 */
export function detailOf(c: DemoCase, over: Partial<CaseDetailOut> = {}): CaseDetailOut {
  const [given = '', ...family] = c.name.split(' ')
  return {
    id: c.id,
    category: c.category,
    status: c.status,
    sentAt: c.sentAt,
    replyBy: c.replyBy,
    statusChangedAt: c.statusChangedAt,
    screening: c.screening,
    isOwn: c.isOwn ?? false,
    personId: `person-${c.id}`,
    givenName: given,
    familyName: family.join(' '),
    title: c.title,
    departmentName: c.department,
    locationName: c.location,
    workEmail: c.email,
    summary: c.isOwn ? null : { status: 'written', createdAt: c.summaryWrittenAt },
    timeline: c.isOwn ? null : c.entries,
    ...over,
  }
}
