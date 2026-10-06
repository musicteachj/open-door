import { hashKey, MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'
import { getGetMeQueryKey, getMe } from '@/api/generated'
import { ApiError } from './api-fetch'

// The retry rules live only in this file. A per-call `retry` would let a query swallow a 401, so
// onUnauthorized never runs, or resend a write after a 403. Writes never retry. A test
// (no-retry-overrides.test.ts) fails if any other source file sets `retry` or `retryDelay`.

interface QueryClientOptions {
  /**
   * Called when /me or a mutation gets a 401: the session is gone. A write passes when it was
   * submitted (ms since the epoch), so the caller can ignore one that began before an identity reset.
   * Any other read's 401 is not taken at its word: /me is asked first (see below).
   */
  onUnauthorized: (requestStartedAt?: number) => void
  /** A fixed wait before the one retry. Tests set 0; the default backs off. */
  retryDelayMs?: number
}

/** A 4xx means the server understood and said no, so asking again cannot help. */
function retryOnce(failureCount: number, error: Error): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false
  return failureCount < 1
}

/**
 * The query rules, set once. Reads retry a 5xx or a network failure once and never a 4xx.
 * Mutations never retry, so a write is never sent twice by accident.
 */
export function createQueryClient({ onUnauthorized, retryDelayMs }: QueryClientOptions) {
  const isUnauthorized = (error: Error) => error instanceof ApiError && error.status === 401
  const meHash = hashKey(getGetMeQueryKey())
  const client: QueryClient = new QueryClient({
    // A read in flight at a reset is canceled silently by clear(), so only writes need the time.
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (!isUnauthorized(error)) return
        if (query.queryHash === meHash) return onUnauthorized()
        // A read's 401 has no time to compare, and another tab's sign-out or switch (which rotates
        // the cookie) causes one too while the sandbox lives. So ask /me: a 401 there reaches this
        // handler as /me's own and marks the session expired; a different person updates the /me
        // cache, which the session guard turns into a reset; the same person was a stale read.
        void client
          .fetchQuery({ queryKey: getGetMeQueryKey(), queryFn: () => getMe() })
          .catch(() => {})
      },
    }),
    mutationCache: new MutationCache({
      onError: (error, _variables, _result, mutation) => {
        if (isUnauthorized(error)) onUnauthorized(mutation.state.submittedAt)
      },
    }),
    defaultOptions: {
      queries: {
        retry: retryOnce,
        ...(retryDelayMs === undefined ? {} : { retryDelay: retryDelayMs }),
      },
      mutations: { retry: false },
    },
  })
  return client
}
