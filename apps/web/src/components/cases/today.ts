import { calendarDayIn } from '@/components/timeoff/dates'

/** Today's calendar date ("2026-10-26") in `timeZone`: the viewer's location, not the browser's. */
export function todayIn(timeZone: string, now: Date = new Date()): string {
  return calendarDayIn(now.toISOString(), timeZone)
}
