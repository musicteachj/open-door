import { QueryClientProvider, useQuery } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { delay, http, HttpResponse } from 'msw'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getAssistantBudget,
  getCurrentConversation,
  getMe,
  getGetAssistantBudgetQueryKey,
  getGetCurrentConversationQueryKey,
  getGetMeQueryKey,
} from '@/api/generated'
import { resetIdentity } from '@/lib/identity'
import { createQueryClient } from '@/lib/query-client'
import { stubAbsoluteUrls } from '@/test/absolute-urls'
import { conversationOut } from '@/test/fake-assistant'
import { server } from '@/test/msw'
import {
  invalidateTimeOff,
  useCancelTimeOff,
  useCreateTimeOff,
  useDecideTimeOff,
  useTimeOffBalances,
  useTimeOffCalendar,
  useTimeOffRequests,
  useTimeOffSummary,
} from './use-time-off'

const url = (path: string) => `${window.location.origin}${path}`
const REQUEST_ID = 'c0ffee00-0000-4000-8000-0000000000c1'

function setup() {
  const queryClient = createQueryClient({ onUnauthorized: vi.fn<() => void>(), retryDelayMs: 0 })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return { queryClient, wrapper }
}

/** Counts the reads of every route a time-off write must refresh, and answers the writes. */
function installApi() {
  const reads = {
    balances: 0,
    requests: 0,
    calendar: 0,
    summary: 0,
    conversation: 0,
    budget: 0,
    me: 0,
  }
  const writes = { held: null as Promise<void> | null }
  const request = {
    id: REQUEST_ID,
    status: 'pending',
  }
  server.use(
    http.get(url('/api/v1/time-off/balances'), () => {
      reads.balances++
      return HttpResponse.json({
        personId: 'p1',
        today: '2026-10-20',
        pto: {},
        sick: [],
        rules: [],
      })
    }),
    http.get(url('/api/v1/time-off/requests'), () => {
      reads.requests++
      return HttpResponse.json({ items: [] })
    }),
    http.get(url('/api/v1/time-off/calendar'), () => {
      reads.calendar++
      return HttpResponse.json({ scheduledWeekdays: [1, 2, 3, 4, 5] })
    }),
    http.get(url('/api/v1/time-off/summary'), () => {
      reads.summary++
      return HttpResponse.json({ ptoAvailableMinutes: 0, pendingCount: 0 })
    }),
    http.get(url('/api/v1/assistant/conversations/current'), () => {
      reads.conversation++
      return HttpResponse.json(conversationOut())
    }),
    http.get(url('/api/v1/assistant/budget'), () => {
      reads.budget++
      return HttpResponse.json({ sandboxReached: false, dailyReached: false })
    }),
    http.get(url('/api/v1/me'), () => {
      reads.me++
      return HttpResponse.json({ id: 'p1' })
    }),
    http.post(url('/api/v1/time-off/requests'), async () => {
      await writes.held
      return HttpResponse.json(request, { status: 201 })
    }),
    http.post(url('/api/v1/time-off/requests/:id/decision'), async () => {
      await writes.held
      return HttpResponse.json(request)
    }),
    http.post(url('/api/v1/time-off/requests/:id/cancel'), async () => {
      await writes.held
      return HttpResponse.json(request)
    }),
  )
  return { reads, writes }
}

const BOOKING = { type: 'pto', startDate: '2026-11-02', endDate: '2026-11-02' } as const

/** Every query the page would hold open, so each has a cached copy and an observer. */
function useEverything() {
  const balances = useTimeOffBalances()
  const requests = useTimeOffRequests({ scope: 'mine' })
  const calendar = useTimeOffCalendar({ from: '2026-11-01', to: '2026-11-30' })
  const summary = useTimeOffSummary()
  const conversation = useQuery({
    queryKey: getGetCurrentConversationQueryKey(),
    queryFn: ({ signal }) => getCurrentConversation({ signal }),
  })
  const budget = useQuery({
    queryKey: getGetAssistantBudgetQueryKey(),
    queryFn: ({ signal }) => getAssistantBudget({ signal }),
  })
  const me = useQuery({
    queryKey: getGetMeQueryKey(),
    queryFn: ({ signal }) => getMe({ signal }),
  })
  return [balances, requests, calendar, summary, conversation, budget, me].every(
    (query) => query.isSuccess,
  )
}

type Reads = ReturnType<typeof installApi>['reads']
const READS_AFTER_ONE_REFRESH: Reads = {
  balances: 2,
  requests: 2,
  calendar: 2,
  summary: 2,
  conversation: 2,
  budget: 2,
  // Not a time-off or conversation read: never refreshed by a time-off write.
  me: 1,
}

beforeEach(() => {
  stubAbsoluteUrls()
})
afterEach(() => {
  resetIdentity(setup().queryClient)
})

describe('invalidateTimeOff', () => {
  it('reads again every time-off query, the conversation, and the budget, and nothing else', async () => {
    const { reads } = installApi()
    const { queryClient, wrapper } = setup()
    const { result } = renderHook(useEverything, { wrapper })
    await waitFor(() => expect(result.current).toBe(true))

    await act(() => invalidateTimeOff(queryClient))

    await waitFor(() => expect(reads).toEqual(READS_AFTER_ONE_REFRESH))
  })
})

describe('the writes', () => {
  const writes = [
    [
      'creating a request',
      () => useCreateTimeOff(),
      (hook: ReturnType<typeof useCreateTimeOff>) => hook.mutate({ data: BOOKING }),
    ],
    [
      'deciding a request',
      () => useDecideTimeOff(),
      (hook: ReturnType<typeof useDecideTimeOff>) =>
        hook.mutate({ requestId: REQUEST_ID, data: { decision: 'deny', note: 'Sorry.' } }),
    ],
    [
      'canceling a request',
      () => useCancelTimeOff(),
      (hook: ReturnType<typeof useCancelTimeOff>) => hook.mutate({ requestId: REQUEST_ID }),
    ],
  ] as const

  it.each(writes)(
    'after %s, reads time off and the conversation again and never sets query data',
    async (_name, useWrite, run) => {
      const { reads } = installApi()
      const { queryClient, wrapper } = setup()
      const read = renderHook(useEverything, { wrapper })
      await waitFor(() => expect(read.result.current).toBe(true))
      const setQueryData = vi.spyOn(queryClient, 'setQueryData')
      const setQueriesData = vi.spyOn(queryClient, 'setQueriesData')
      const write = renderHook(useWrite as () => never, { wrapper })

      act(() => run(write.result.current as never))

      await waitFor(() => expect(reads).toEqual(READS_AFTER_ONE_REFRESH))
      expect(setQueryData).not.toHaveBeenCalled()
      expect(setQueriesData).not.toHaveBeenCalled()
    },
  )

  it('reads again when the write fails, since the server may have changed anyway', async () => {
    const { reads } = installApi()
    server.use(
      http.post(url('/api/v1/time-off/requests/:id/cancel'), () =>
        HttpResponse.json(
          { type: 'status-changed', title: 'x', status: 409, instance: '/x' },
          { status: 409, headers: { 'Content-Type': 'application/problem+json' } },
        ),
      ),
    )
    const { wrapper } = setup()
    const read = renderHook(useEverything, { wrapper })
    await waitFor(() => expect(read.result.current).toBe(true))
    const write = renderHook(() => useCancelTimeOff(), { wrapper })

    act(() => write.result.current.mutate({ requestId: REQUEST_ID }))

    await waitFor(() => expect(write.result.current.isError).toBe(true))
    await waitFor(() => expect(reads).toEqual(READS_AFTER_ONE_REFRESH))
  })

  it('leaves nothing of the old person in the new cache when a write finishes after a switch', async () => {
    const { reads, writes: held } = installApi()
    const { queryClient, wrapper } = setup()
    const read = renderHook(useEverything, { wrapper })
    await waitFor(() => expect(read.result.current).toBe(true))
    let release!: () => void
    held.held = new Promise<void>((resolve) => {
      release = resolve
    })
    const setQueryData = vi.spyOn(queryClient, 'setQueryData')
    const write = renderHook(() => useCreateTimeOff(), { wrapper })
    act(() => write.result.current.mutate({ data: BOOKING }))
    await waitFor(() => expect(write.result.current.isPending).toBe(true))
    // The persona switches while the write is still in flight: the old observers go with the
    // shell, and the cache is cleared.
    read.unmount()
    act(() => resetIdentity(queryClient))
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0)
    const before = { ...reads }

    release()
    await waitFor(() => expect(write.result.current.isSuccess).toBe(true))

    // The old person's answer (a created request) went nowhere: no data was set, the cache holds
    // nothing, and no query was started for a person who is no longer here.
    expect(setQueryData).not.toHaveBeenCalled()
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0)
    expect(reads).toEqual(before)
  })

  it('only refreshes what the new person is looking at when a late write finishes', async () => {
    const { reads, writes: held } = installApi()
    const { queryClient, wrapper } = setup()
    let release!: () => void
    held.held = new Promise<void>((resolve) => {
      release = resolve
    })
    const write = renderHook(() => useDecideTimeOff(), { wrapper })
    act(() => write.result.current.mutate({ requestId: REQUEST_ID, data: { decision: 'approve' } }))
    await waitFor(() => expect(write.result.current.isPending).toBe(true))
    act(() => resetIdentity(queryClient))
    // The new person's page reads its own summary.
    const fresh = renderHook(() => useTimeOffSummary(), { wrapper })
    await waitFor(() => expect(fresh.result.current.isSuccess).toBe(true))
    expect(reads.summary).toBe(1)

    release()
    await delay(0)
    await waitFor(() => expect(write.result.current.isSuccess).toBe(true))

    // The new person's summary is read again (their own data), and nothing from the old write
    // is written into it.
    await waitFor(() => expect(reads.summary).toBe(2))
    expect(fresh.result.current.data).toEqual({ ptoAvailableMinutes: 0, pendingCount: 0 })
  })
})

describe('the read hooks', () => {
  it('give each query a stable key from its parameters', async () => {
    installApi()
    const { queryClient, wrapper } = setup()
    renderHook(
      () => {
        useTimeOffRequests({ scope: 'team', from: '2026-11-01', to: '2026-11-30' })
        useTimeOffRequests({ scope: 'mine' })
        useTimeOffBalances()
        useTimeOffCalendar({ from: '2026-11-01', to: '2026-11-30' })
        useTimeOffSummary()
      },
      { wrapper },
    )
    const keys = queryClient
      .getQueryCache()
      .getAll()
      .map((query) => query.queryKey)
    expect(keys).toEqual(
      expect.arrayContaining([
        ['/api/v1/time-off/requests', { scope: 'team', from: '2026-11-01', to: '2026-11-30' }],
        ['/api/v1/time-off/requests', { scope: 'mine' }],
        ['/api/v1/time-off/balances'],
        ['/api/v1/time-off/calendar', { from: '2026-11-01', to: '2026-11-30' }],
        ['/api/v1/time-off/summary'],
      ]),
    )
  })
})
