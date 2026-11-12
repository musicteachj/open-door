import { ApiError } from '@/lib/api-fetch'

/** Shown when starting a sandbox fails: on the landing page, and from the budget banner. */
export const SANDBOX_START_FAILED = "We couldn't start a sandbox."

// The four refusals the API makes before it starts a sandbox. Each carries its approved text as the
// problem's `detail` (apps/api/app/modules/sandbox/texts.py), so the web app holds no copy of them.
// Only a failed or unreachable check can succeed on a second try; a limit cannot.
const REFUSAL_RETRY: Record<string, boolean> = {
  'sandbox-start-limit': false,
  'sandbox-day-limit': false,
  'turnstile-failed': true,
  'turnstile-unavailable': true,
}

/**
 * What to tell the visitor when starting a sandbox failed, and whether Retry can help. A refusal
 * says its own text; any other failure keeps the plain one with Retry.
 */
export function sandboxStartError(error: unknown): { message: string; canRetry: boolean } {
  if (error instanceof ApiError) {
    const type = error.problem?.type
    const detail = error.problem?.detail
    if (type && type in REFUSAL_RETRY && typeof detail === 'string' && detail) {
      return { message: detail, canRetry: REFUSAL_RETRY[type]! }
    }
  }
  return { message: SANDBOX_START_FAILED, canRetry: true }
}
