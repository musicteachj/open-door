const MINUTE_MS = 60_000
const HOUR_MS = 60 * MINUTE_MS

/** The banner and the sandbox indicator show the exact time at or under this. */
const EXPIRING_SOON_MS = 3 * HOUR_MS

/**
 * How long a sandbox has left. Three hours or more is whole hours, rounded down ("21 h"). Under
 * three hours is hours and minutes ("2 h 50 min", "2 h" on the hour), under an hour is minutes
 * ("45 min"), and under a minute, or already past, is "less than a minute".
 */
export function formatTimeLeft(msLeft: number): string {
  if (!Number.isFinite(msLeft)) return 'less than a minute'
  if (msLeft >= EXPIRING_SOON_MS) return `${Math.floor(msLeft / HOUR_MS)} h`
  const totalMinutes = Math.floor(Math.max(msLeft, 0) / MINUTE_MS)
  if (totalMinutes < 1) return 'less than a minute'
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (hours === 0) return `${minutes} min`
  return minutes === 0 ? `${hours} h` : `${hours} h ${minutes} min`
}

/** True at three hours or less, which is when the expiry banner appears. */
export function isExpiringSoon(msLeft: number): boolean {
  return msLeft <= EXPIRING_SOON_MS
}

/** The hour (0 to 23) on the wall clock in an IANA timezone. */
function hourIn(now: Date, timeZone: string): number {
  const parts = new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    hourCycle: 'h23',
    timeZone,
  }).formatToParts(now)
  return Number(parts.find((part) => part.type === 'hour')?.value)
}

/**
 * "Good morning" from 05:00 to 11:59, "Good afternoon" to 16:59, and "Good evening" otherwise, by
 * the clock in the location's timezone, not the browser's or UTC.
 */
export function greetingFor(now: Date, timeZone: string): string {
  const hour = hourIn(now, timeZone)
  if (hour >= 5 && hour < 12) return 'Good morning'
  if (hour >= 12 && hour < 17) return 'Good afternoon'
  return 'Good evening'
}

/** The assistant home's heading: "Good morning, Priya." */
export function greetingLine(now: Date, timeZone: string, firstName: string): string {
  return `${greetingFor(now, timeZone)}, ${firstName}.`
}

/**
 * "2026-09-12" as "Sep 12, 2026", the handbook's date. A calendar date, so no timezone moves it.
 * Text that isn't a date comes back unchanged.
 */
export function formatShortDate(isoDate: string): string {
  const date = new Date(`${isoDate}T00:00:00Z`)
  if (Number.isNaN(date.getTime())) return isoDate
  return date.toLocaleDateString('en-US', { dateStyle: 'medium', timeZone: 'UTC' })
}
