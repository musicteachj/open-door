import { ApiError } from '@/lib/api-fetch'

/**
 * Whether the API said "no such thing" (a 404). A page that loads one person or one record asks
 * this of its error and shows the not-found page, so every screen words a missing thing the same
 * way. The route error boundary asks it too, so a page may also just let the error through.
 */
export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404
}

/** The response's full X-Request-ID, or null (a network failure has no response). */
export function requestIdOf(error: unknown): string | null {
  return error instanceof ApiError ? error.requestId : null
}
