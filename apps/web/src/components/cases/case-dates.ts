// How the case components show dates. A reply-by date is a calendar date and never moves with a
// time zone. A sent or status time is a UTC timestamp, shown in the viewer's location's zone.
import { formatterFor } from '@/lib/time'

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
  // Newer ICU puts a narrow no-break space before AM and PM; a plain space reads the same and
  // matches the design's copy.
  return formatterFor(timeZone, CLOCK).format(new Date(timestamp)).replace(/[  ]/g, ' ')
}

/** "Mon, Oct 26, 10:41 AM MDT". */
export function dateTimeInZone(timestamp: string, timeZone: string): string {
  return `${dayInZone(timestamp, timeZone)}, ${timeInZone(timestamp, timeZone)}`
}

/** The calendar day of a timestamp in `timeZone`, as a key to compare two timestamps by. */
export function dayKeyInZone(timestamp: string, timeZone: string): string {
  return formatterFor(timeZone, { year: 'numeric', month: '2-digit', day: '2-digit' }).format(
    new Date(timestamp),
  )
}

// claude-opus-5-5, claude-opus-5, and the dated ids (claude-sonnet-4-20250514). A date is dropped.
const MODEL_ID = /^claude-(opus|sonnet|haiku)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?$/

/** "claude-opus-5-5" as "Claude Opus 5.5". An id this doesn't know comes back unchanged. */
export function modelDisplayName(modelId: string): string {
  const match = MODEL_ID.exec(modelId)
  if (!match) return modelId
  const [, family, major, minor] = match
  const version = minor === undefined ? major : `${major}.${minor}`
  return `Claude ${family![0]!.toUpperCase()}${family!.slice(1)} ${version}`
}
