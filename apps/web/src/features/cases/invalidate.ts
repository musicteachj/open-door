import type { QueryClient } from '@tanstack/react-query'
import { invalidateConversation } from '@/features/chat/use-conversation'

/** Every case route's key starts with this, so one prefix match reaches them all. */
const CASES_PREFIX = '/api/v1/cases'

/** Reads every `/api/v1/cases` query again (the lists, the counts, a detail's metadata). */
export function invalidateCases(queryClient: QueryClient) {
  return queryClient.invalidateQueries({
    predicate: ({ queryKey }) =>
      typeof queryKey[0] === 'string' && queryKey[0].startsWith(CASES_PREFIX),
  })
}

/** After a case is sent: the case lists, and the conversation (the turn gains `caseOpened`). */
export function invalidateAfterSend(queryClient: QueryClient) {
  return Promise.all([invalidateCases(queryClient), invalidateConversation(queryClient)])
}
