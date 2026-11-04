// How the case components show dates. A reply-by date is a calendar date and never moves with a
// time zone. A sent or status time is a UTC timestamp, shown in the viewer's location's zone.
import { calendarDayIn } from '@/components/timeoff/dates'
import { formatterFor, plainSpaces } from '@/lib/time'

const DAY = { weekday: 'short', month: 'short', day: 'numeric' } as const
const CLOCK = { hour: 'numeric', minute: '2-digit', timeZoneName: 'short' } as const

/** "2026-10-28" as "Wed, Oct 28". A calendar date: no zone shifts it. */
export function formatCalendarDate(isoDate: string): string {
  return formatterFor('UTC', DAY).format(new Date(`${isoDate}T00:00:00Z`))
}

/** A timestamp's day in `timeZone`: "Mon, Oct 26". */
export function dayInZone(timestamp: string, timeZone: string): string {
  return formatterFor(timeZone, DAY).format(new Date(timestamp))
}

/** A timestamp's clock time in `timeZone`, with its abbreviation: "10:41 AM MDT". */
export function timeInZone(timestamp: string, timeZone: string): string {
  return plainSpaces(formatterFor(timeZone, CLOCK).format(new Date(timestamp)))
}

/** "Mon, Oct 26, 10:41 AM MDT". */
export function dateTimeInZone(timestamp: string, timeZone: string): string {
  return `${dayInZone(timestamp, timeZone)}, ${timeInZone(timestamp, timeZone)}`
}

/** The calendar day of a timestamp in `timeZone`, as a key to compare two timestamps by. */
export function dayKeyInZone(timestamp: string, timeZone: string): string {
  return calendarDayIn(timestamp, timeZone)
}
