import { http, HttpResponse } from 'msw'
import type {
  BalancesOut,
  CalendarOut,
  CheckOut,
  PossibleRequest,
  RequestOut,
  SummaryOut,
} from '@/api/generated'
import {
  CHECK_ONE_DAY,
  MARCUS,
  MINE_APPROVED,
  MINE_CANCELED,
  MINE_DENIED,
  MINE_RECORDED,
  PRIYA,
  PRIYA_WAITING,
  PTO_BALANCE,
  PTO_RULE,
  SICK_RULE,
  SICK_YEAR,
  TEAM_APPROVED,
  TEAM_DENIED,
  TEAM_SICK,
  TODAY,
  ZARA_WAITING,
} from '@/app/gallery/fixtures/timeoff'
import { server } from './msw'

// A fake of the time-off routes for the page tests: Priya Raman's balances and requests and
// Marcus Bell's queue (the gallery's fixtures, so the figures are the design's), and writes that
// change what the next read says, as the real server does. Every figure and label is written in
// the fixtures by hand; nothing here works one out.

const url = (path: string) => `${window.location.origin}${path}`

function problem(status: number, type: string, detail: string, extra: object = {}) {
  return HttpResponse.json(
    { type, title: type, status, instance: '/api/v1/time-off', detail, ...extra },
    { status, headers: { 'X-Request-ID': 'b'.repeat(32) } },
  )
}

export type FakeTimeOffOptions = {
  /** Priya's own requests (the Time off page). Defaults to the design's five. */
  mine?: RequestOut[]
  /** What waits for Marcus (the Approvals page). Defaults to Zara's and Priya's. */
  waiting?: RequestOut[]
  /** Everyone below Marcus: Coming up and Recent decisions read these. */
  team?: RequestOut[]
  balances?: Partial<BalancesOut>
  calendar?: Partial<CalendarOut>
  /** Whether the person is a manager (the summary's `waitingCount`). */
  manager?: boolean
}

type Call = { scope: string | null; from: string | null; to: string | null }

export function installFakeTimeOff(options: FakeTimeOffOptions = {}) {
  const state = {
    mine: [...(options.mine ?? [MINE_APPROVED, MINE_CANCELED, MINE_RECORDED, MINE_DENIED])],
    waiting: [...(options.waiting ?? [ZARA_WAITING, PRIYA_WAITING])],
    team: [...(options.team ?? [TEAM_SICK, TEAM_APPROVED, TEAM_DENIED])],
    manager: options.manager ?? false,
    /** What `POST /check` answers: a function of the body, or a promise to hold it. */
    check: (_body: PossibleRequest): CheckOut | Promise<CheckOut> => CHECK_ONE_DAY,
    /** What `POST /requests` answers when it fails, or null to book. */
    createFailure: null as { status: number; type: string; detail: string } | null,
    /** What a decision answers when it is refused. */
    /** `currentStatus` is a 409's status for the request; `null` leaves it out, as an odd server might. */
    decideFailure: null as {
      status: number
      type: string
      detail: string
      currentStatus?: string | null
    } | null,
    cancelFailure: null as { status: number; type: string; detail: string } | null,
    /** Held until a test releases it, so a test can look at the "in flight" state. */
    holdDecision: null as Promise<void> | null,
    holdCancel: null as Promise<void> | null,
    holdCreate: null as Promise<void> | null,
    /** Called before each requests read answers, so a test can hold or fail a refetch. */
    holdRequests: null as ((scope: string | null) => Promise<void> | undefined) | null,
    /** Requests that left the queue because they were canceled, by id. */
    gone: new Map<string, string>(),
  }
  const calls = {
    balances: 0,
    requests: [] as Call[],
    calendar: 0,
    /** The window each calendar read asked for (`from` is null when the page leaves it to the API). */
    calendarWindows: [] as { from: string | null; to: string | null }[],
    summary: 0,
    checks: [] as PossibleRequest[],
    creates: [] as PossibleRequest[],
    decisions: [] as { id: string; body: { decision: string; note?: string | null } }[],
    cancels: [] as string[],
  }
  let nextId = 1

  const summary = (): SummaryOut => ({
    ptoAvailableMinutes: PTO_BALANCE.availableMinutes,
    ptoAvailableLabel: PTO_BALANCE.availableLabel,
    pendingCount: state.mine.filter((request) => request.status === 'pending').length,
    approver: MARCUS,
    waitingCount: state.manager ? state.waiting.length : null,
    today: TODAY,
  })

  server.use(
    http.get(url('/api/v1/time-off/balances'), () => {
      calls.balances++
      const balances: BalancesOut = {
        personId: PRIYA.id,
        today: TODAY,
        pto: PTO_BALANCE,
        sick: [SICK_YEAR],
        rules: [PTO_RULE, SICK_RULE],
        ...options.balances,
      }
      return HttpResponse.json(balances)
    }),
    http.get(url('/api/v1/time-off/requests'), async ({ request }) => {
      const params = new URL(request.url).searchParams
      const scope = params.get('scope')
      calls.requests.push({ scope, from: params.get('from'), to: params.get('to') })
      const from = params.get('from')
      const to = params.get('to')
      // As the API does: waiting is shown whenever its days fall, the others only if their days
      // meet the window.
      const meets = (item: RequestOut) =>
        (to === null || item.startDate <= to) && (from === null || item.endDate >= from)
      // And `decided` is the caller's own decisions, newest first, bounded by the day each was made.
      const decidedByMarcus = (item: RequestOut) =>
        (item.status === 'approved' || item.status === 'denied') &&
        item.decidedBy?.id === MARCUS.id &&
        item.decidedAt !== null &&
        (from === null || item.decidedAt.slice(0, 10) >= from) &&
        (to === null || item.decidedAt.slice(0, 10) <= to)
      const items =
        scope === 'waiting'
          ? state.waiting
          : scope === 'decided'
            ? state.team
                .filter(decidedByMarcus)
                .sort((a, b) => b.decidedAt!.localeCompare(a.decidedAt!))
            : (scope === 'team' ? state.team : state.mine).filter(meets)
      await state.holdRequests?.(scope)
      return HttpResponse.json({ items, fromDate: TODAY, toDate: TODAY })
    }),
    http.get(url('/api/v1/time-off/calendar'), ({ request }) => {
      calls.calendar++
      const params = new URL(request.url).searchParams
      calls.calendarWindows.push({ from: params.get('from'), to: params.get('to') })
      const calendar: CalendarOut = {
        scheduledWeekdays: [1, 2, 3, 4, 5],
        dayMinutes: 480,
        dayLabel: '8 hours',
        holidays: [{ day: '2026-11-26', name: 'Thanksgiving' }],
        earliestStart: { pto: TODAY, sick: '2026-09-20' },
        latestEnd: '2027-12-31',
        sickLookbackDays: 30,
        halfDayMinutes: 240,
        halfDayLabel: '4 hours',
        ...options.calendar,
      }
      return HttpResponse.json(calendar)
    }),
    http.get(url('/api/v1/time-off/summary'), () => {
      calls.summary++
      return HttpResponse.json(summary())
    }),
    http.post(url('/api/v1/time-off/check'), async ({ request }) => {
      const body = (await request.json()) as PossibleRequest
      calls.checks.push(body)
      return HttpResponse.json(await state.check(body))
    }),
    http.post(url('/api/v1/time-off/requests'), async ({ request }) => {
      const body = (await request.json()) as PossibleRequest
      calls.creates.push(body)
      await state.holdCreate
      if (state.createFailure) {
        const { status, type, detail } = state.createFailure
        return problem(status, type, detail)
      }
      const sick = body.type === 'sick'
      const created: RequestOut = {
        ...PRIYA_WAITING,
        id: `created-${nextId++}`,
        type: body.type,
        startDate: body.startDate,
        endDate: body.endDate,
        partialMinutes: body.partialMinutes ?? null,
        status: sick ? 'recorded' : 'pending',
        availableAfterLabel: null,
        availableAfterMinutes: null,
        coverage: null,
      }
      state.mine = [...state.mine, created]
      return HttpResponse.json(created, { status: 201 })
    }),
    http.post(url('/api/v1/time-off/requests/:id/decision'), async ({ request, params }) => {
      const id = String(params.id)
      const body = (await request.json()) as { decision: string; note?: string | null }
      calls.decisions.push({ id, body })
      await state.holdDecision
      if (state.decideFailure) {
        const { status, type, detail, currentStatus = 'canceled' } = state.decideFailure
        return problem(
          status,
          type,
          detail,
          status === 409 && currentStatus !== null ? { currentStatus } : {},
        )
      }
      const found = state.waiting.find((item) => item.id === id)
      if (!found) {
        // Not pending any more: the API says 409 with the status it has now.
        const now = state.gone.get(id) ?? state.team.find((item) => item.id === id)?.status
        return now
          ? problem(409, 'status-changed', 'This request has changed since the page was loaded.', {
              currentStatus: now,
            })
          : problem(404, 'not-found', 'That request could not be found.')
      }
      state.waiting = state.waiting.filter((item) => item.id !== id)
      const decided: RequestOut = {
        ...found,
        status: body.decision === 'approve' ? 'approved' : 'denied',
        decidedBy: MARCUS,
        decidedAt: `${TODAY}T18:00:00Z`,
        decisionNote: body.note ?? null,
      }
      state.team = [decided, ...state.team]
      return HttpResponse.json(decided)
    }),
    http.post(url('/api/v1/time-off/requests/:id/cancel'), async ({ params }) => {
      const id = String(params.id)
      calls.cancels.push(id)
      await state.holdCancel
      if (state.cancelFailure) {
        const { status, type, detail } = state.cancelFailure
        return problem(status, type, detail, { currentStatus: 'canceled' })
      }
      const found = state.mine.find((item) => item.id === id)
      if (!found) return problem(404, 'not-found', 'That request could not be found.')
      const canceled: RequestOut = {
        ...found,
        status: 'canceled',
        canceledAt: `${TODAY}T18:00:00Z`,
      }
      state.mine = state.mine.map((item) => (item.id === id ? canceled : item))
      // The manager's queue no longer holds it, and a decision on it now says why.
      if (state.waiting.some((item) => item.id === id)) {
        state.waiting = state.waiting.filter((item) => item.id !== id)
        state.gone.set(id, 'canceled')
      }
      return HttpResponse.json(canceled)
    }),
  )

  return {
    state,
    calls,
    /** Takes a waiting request off the queue without anyone deciding it here (a cancel elsewhere). */
    dropWaiting: (id: string, becameStatus = 'canceled') => {
      state.waiting = state.waiting.filter((item) => item.id !== id)
      state.gone.set(id, becameStatus)
    },
  }
}

/** A promise a test settles itself, to hold a response. */
export function gate() {
  let open = () => {}
  const promise = new Promise<void>((resolve) => {
    open = resolve
  })
  return { promise, open }
}
