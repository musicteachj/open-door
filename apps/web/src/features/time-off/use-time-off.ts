import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import {
  useCancelTimeOffRequest,
  useCheckTimeOffRequest,
  useCreateTimeOffRequest,
  useDecideTimeOffRequest,
  useGetTimeOffBalances,
  useGetTimeOffCalendar,
  useGetTimeOffSummary,
  useListTimeOffRequests,
  type GetTimeOffBalancesParams,
  type GetTimeOffCalendarParams,
  type ListTimeOffRequestsParams,
} from '@/api/generated'
import { invalidateConversation } from '@/features/chat/use-conversation'

// The time-off hooks the pages and the confirm card use. The reads are the generated ones under
// names the pages share, so each query keeps the generated key (its route, then its parameters).
// Every write ends by reading again, never by setting data: a write that finishes after a persona
// switch must not put the old person's answer into the new person's cache (see the backlog's
// "Keep a write from the old identity out of the new cache").

/** Every time-off route's key starts with this, so one prefix match reaches them all. */
const TIME_OFF_PREFIX = '/api/v1/time-off'

/**
 * Reads again everything a time-off change can touch: each `/api/v1/time-off` query (balances,
 * requests, the calendar, the summary the rail and the nav read), then the conversation and the
 * budget, since a card's status and a banner follow from them. After a persona switch the cache is
 * empty, so this only refreshes what the new person is looking at.
 */
export function invalidateTimeOff(queryClient: QueryClient) {
  return Promise.all([
    queryClient.invalidateQueries({
      predicate: ({ queryKey }) =>
        typeof queryKey[0] === 'string' && queryKey[0].startsWith(TIME_OFF_PREFIX),
    }),
    invalidateConversation(queryClient),
  ])
}

/**
 * How a page reads one of these. `throwOnError` sends a failed first load to the route's error
 * boundary (the global "Something went wrong" with its reference and Retry), as the handbook does,
 * but never a read again that fails after data was shown: a write ends by reading again, and a
 * blip there must not replace a page the person is using. `enabled` holds a read until what it
 * needs (today's date) is known.
 */
export type ReadOptions = { enabled?: boolean; throwOnError?: boolean }

/** Throw only while there is nothing to show. */
const onlyFirstLoad = (_error: Error, query: { state: { data: unknown } }) =>
  query.state.data === undefined

export const useTimeOffBalances = (
  params?: GetTimeOffBalancesParams,
  { throwOnError = false, enabled = true }: ReadOptions = {},
) =>
  useGetTimeOffBalances(params, {
    query: { throwOnError: throwOnError ? onlyFirstLoad : false, enabled },
  })

export const useTimeOffRequests = (
  params?: ListTimeOffRequestsParams,
  { throwOnError = false, enabled = true }: ReadOptions = {},
) =>
  useListTimeOffRequests(params, {
    query: { throwOnError: throwOnError ? onlyFirstLoad : false, enabled },
  })

export const useTimeOffCalendar = (
  params: GetTimeOffCalendarParams,
  { throwOnError = false, enabled = true }: ReadOptions = {},
) =>
  useGetTimeOffCalendar(params, {
    query: { throwOnError: throwOnError ? onlyFirstLoad : false, enabled },
  })

/**
 * The summary the nav badge, the rail, and the pages' approver line read. `enabled` lets a caller
 * that doesn't need it (the shell, off the assistant home, for someone with no reports) skip it.
 */
export const useTimeOffSummary = ({ enabled = true, throwOnError = false }: ReadOptions = {}) =>
  useGetTimeOffSummary({ query: { enabled, throwOnError: throwOnError ? onlyFirstLoad : false } })

/** What a possible request would count. A mutation, since it is asked on each change and writes nothing. */
export const useCheckTimeOff = () => useCheckTimeOffRequest()

/** Books a request (a PTO request waits for approval, sick time is recorded). */
export function useCreateTimeOff() {
  const queryClient = useQueryClient()
  return useCreateTimeOffRequest({ mutation: { onSettled: () => invalidateTimeOff(queryClient) } })
}

/**
 * A manager approves or denies a request. `onFailure` runs the moment the server refuses, before
 * time off is read again, so a page can hold what it was showing through that read.
 */
export function useDecideTimeOff(onFailure?: (error: Error) => void) {
  const queryClient = useQueryClient()
  return useDecideTimeOffRequest({
    mutation: { onError: onFailure, onSettled: () => invalidateTimeOff(queryClient) },
  })
}

/** The person cancels their own request. */
export function useCancelTimeOff() {
  const queryClient = useQueryClient()
  return useCancelTimeOffRequest({ mutation: { onSettled: () => invalidateTimeOff(queryClient) } })
}
