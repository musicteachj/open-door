import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'
import { ApiError } from './api-fetch'

// The retry rules live only in this file. A per-call `retry` would let a query swallow a 401, so
// onUnauthorized never runs, or resend a write after a 403. Writes never retry. A test
// (no-retry-overrides.test.ts) fails if any other source file sets `retry` or `retryDelay`.

interface QueryClientOptions {
  /**
   * Called when any query or mutation gets a 401: the session is gone. A write passes when it was
   * submitted (ms since the epoch), so the caller can ignore one that began before an identity reset.
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
  return new QueryClient({
    // A read in flight at a reset is canceled silently by clear(), so only writes need the time.
    queryCache: new QueryCache({
      onError: (error) => {
        if (isUnauthorized(error)) onUnauthorized()
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
}
