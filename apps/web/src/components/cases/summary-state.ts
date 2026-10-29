import type { CaseDetailOut, CaseSummaryOut } from '@/api/generated'

/** What the summary block shows. */
export type SummaryState = 'written' | 'pending' | 'failed' | 'crisis'

/** The server allows a retry this long after a case was sent (`RETRY_AFTER` in the case service). */
const SERVER_RETRY_AFTER_MS = 2 * 60_000

/**
 * Extra time before the page offers "Try again". The server's gate reads the database clock and
 * this reads the browser's, so a fast client clock would offer a retry the server refuses.
 */
const CLOCK_MARGIN_MS = 30_000
const RETRY_OFFERED_AFTER_MS = SERVER_RETRY_AFTER_MS + CLOCK_MARGIN_MS

/**
 * Which state the summary block is in, from the detail's metadata and the summary as fetched
 * (null until it arrives). Crisis wins: a crisis case has no summary, by design. No summary yet
 * is `pending`, until two minutes after the case was sent, when it counts as `failed` so "Try
 * again" shows, once the server accepts a retry plus a 30 second margin for clock differences. `now` is a value, not a clock: the
 * page must re-render with a fresh one (a tick, once a case is waiting) or pending never turns
 * into failed on its own. If the retry comes back 409 `summary-retry-refused` (the server's clock
 * says too soon, or one is already running), the page leaves the block pending rather than showing
 * an error: a later tick offers it again. `fetchFailed` is the page's flag for a summary request that errored. Any failure reason, including
 * `screening-conflict` and `unscreened`, shows the same failed state.
 */
export function summaryStateOf(
  detail: Pick<CaseDetailOut, 'screening' | 'sentAt' | 'summary'>,
  fetched: CaseSummaryOut | null,
  now: Date,
  fetchFailed = false,
): SummaryState {
  if (
    detail.screening === 'crisis' ||
    fetched?.reason === 'crisis' ||
    detail.summary?.reason === 'crisis'
  ) {
    return 'crisis'
  }
  if (fetched?.status === 'written') return 'written'
  // `fetched` is null both while loading and after a failed fetch, so the page says which.
  if (fetchFailed) return 'failed'
  if (fetched?.status === 'failed' || detail.summary?.status === 'failed') return 'failed'
  // The detail says it is written, and the text is still on its way.
  if (detail.summary?.status === 'written' && fetched === null) return 'pending'
  // None yet (or written, but the fetch found none): wait, then offer the retry.
  return now.getTime() - Date.parse(detail.sentAt) >= RETRY_OFFERED_AFTER_MS ? 'failed' : 'pending'
}

/**
 * What "Try again" does. After a failed fetch the summary may well exist, so the page fetches it
 * again (`refetch`: a GET, an audited read). Otherwise there is none, and the page asks the server
 * to write one (`rewrite`: POST /cases/{id}/summary). The block only calls `onRetry`; the page
 * picks the request with this.
 */
export function summaryRetryKind(fetchFailed: boolean): 'refetch' | 'rewrite' {
  return fetchFailed ? 'refetch' : 'rewrite'
}
