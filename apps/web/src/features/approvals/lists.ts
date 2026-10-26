import type { RequestOut } from '@/api/generated'
import { addDays } from '@/components/timeoff/dates'

/** "Coming up on your team" looks this far ahead. */
export const COMING_UP_DAYS = 30
/** "Recent decisions" looks this far back, by the day each decision was made. The API's `decided` scope applies it, newest first. */
export const RECENT_DAYS = 90

/**
 * What waits for the manager: PTO still pending, oldest sent first. The API's `waiting` scope
 * already is exactly this; the filter is the page's own guarantee that sick time (recorded, never
 * decided) is never offered as something to decide.
 */
export function waitingRequests(items: RequestOut[]): RequestOut[] {
  return items
    .filter((request) => request.type === 'pto' && request.status === 'pending')
    .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
}

/**
 * Approved PTO and recorded sick time that ends today or later and starts within the next 30 days,
 * soonest first. A PTO request that is only waiting is not off yet, so it is not here.
 */
export function comingUp(items: RequestOut[], today: string): RequestOut[] {
  const horizon = addDays(today, COMING_UP_DAYS)
  return items
    .filter(
      (request) =>
        (request.status === 'approved' || request.status === 'recorded') &&
        request.endDate >= today &&
        request.startDate <= horizon,
    )
    .sort(
      (a, b) => a.startDate.localeCompare(b.startDate) || a.createdAt.localeCompare(b.createdAt),
    )
}
