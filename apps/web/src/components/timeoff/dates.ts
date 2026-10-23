// Leave dates are calendar dates: plain "YYYY-MM-DD" strings, in the location's timezone. They
// are never parsed as a local-time Date, which would move them a day in a zone behind UTC. Every
// helper here goes through UTC, so the browser's own zone cannot change a date.

import { formatterFor } from '@/lib/time'

/** A month on the calendar: the year, and the month from 0 (January) to 11. */
export type CalendarMonth = { year: number; month: number }

const DAY_MS = 86_400_000

const longFormat = formatterFor('UTC', {
  weekday: 'long',
  month: 'long',
  day: 'numeric',
})
const shortFormat = formatterFor('UTC', {
  weekday: 'short',
  month: 'short',
  day: 'numeric',
})
const monthDayFormat = formatterFor('UTC', {
  month: 'long',
  day: 'numeric',
})
const monthFormat = formatterFor('UTC', {
  month: 'long',
  year: 'numeric',
})

/** Sunday first, as the date picker's columns run. */
export const WEEKDAY_NAMES = [
  'Sunday',
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
] as const

function toUtc(day: string): Date {
  const [year = 0, month = 1, date = 1] = day.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, date))
}

function toDay(date: Date): string {
  const year = String(date.getUTCFullYear()).padStart(4, '0')
  const month = String(date.getUTCMonth() + 1).padStart(2, '0')
  const dayOfMonth = String(date.getUTCDate()).padStart(2, '0')
  return `${year}-${month}-${dayOfMonth}`
}

/** "Friday, October 30" from "2026-10-30". */
export function longDate(day: string): string {
  return longFormat.format(toUtc(day))
}

/** "Fri, Oct 30" from "2026-10-30", for the Dates field. */
export function shortDate(day: string): string {
  return shortFormat.format(toUtc(day))
}

/** "September 20" from "2026-09-20", for a sentence. */
export function monthDay(day: string): string {
  return monthDayFormat.format(toUtc(day))
}

/** "Wednesday, November 25 to Friday, November 27", or one day when the ends are the same. */
export function longRange(start: string, end: string): string {
  return start === end ? longDate(start) : `${longDate(start)} to ${longDate(end)}`
}

/** "Wed, Nov 25 to Fri, Nov 27", or one day when the ends are the same. */
export function shortRange(start: string, end: string): string {
  return start === end ? shortDate(start) : `${shortDate(start)} to ${shortDate(end)}`
}

/** "November 9 to 10" for a range in one month, "October 30" for one day, for a button's name. */
export function monthDayRange(start: string, end: string): string {
  if (start === end) return monthDay(start)
  const sameMonth = start.slice(0, 7) === end.slice(0, 7)
  return sameMonth
    ? `${monthDay(start)} to ${toUtc(end).getUTCDate()}`
    : `${monthDay(start)} to ${monthDay(end)}`
}

/** The calendar day ("YYYY-MM-DD") that a moment falls on in an IANA time zone. */
export function calendarDayIn(isoTimestamp: string, timeZone: string): string {
  const parts = formatterFor(timeZone, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date(isoTimestamp))
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? ''
  return `${part('year')}-${part('month')}-${part('day')}`
}

/** 1 for Monday through 7 for Sunday, as the API numbers a person's scheduled weekdays. */
export function isoWeekday(day: string): number {
  return toUtc(day).getUTCDay() || 7
}

/** The weekday from 0 (Sunday) to 6 (Saturday), the picker's column. */
export function columnOf(day: string): number {
  return toUtc(day).getUTCDay()
}

export function addDays(day: string, days: number): string {
  return toDay(new Date(toUtc(day).getTime() + days * DAY_MS))
}

/** The same date in another month, or that month's last day when it is shorter. */
export function addMonths(day: string, months: number): string {
  const date = toUtc(day)
  const target = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + months, 1))
  const lastDay = new Date(
    Date.UTC(target.getUTCFullYear(), target.getUTCMonth() + 1, 0),
  ).getUTCDate()
  target.setUTCDate(Math.min(date.getUTCDate(), lastDay))
  return toDay(target)
}

/** Negative when `a` is earlier, positive when later, 0 for the same day. */
export function compareDays(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0
}

export function monthOf(day: string): CalendarMonth {
  const date = toUtc(day)
  return { year: date.getUTCFullYear(), month: date.getUTCMonth() }
}

/** The month's first day: { 2026, 9 } is "2026-10-01". */
export function firstOfMonth({ year, month }: CalendarMonth): string {
  return toDay(new Date(Date.UTC(year, month, 1)))
}

/** The month's last day: { 2026, 9 } is "2026-10-31". */
export function lastOfMonth({ year, month }: CalendarMonth): string {
  return toDay(new Date(Date.UTC(year, month + 1, 0)))
}

/** The month before (-1) or after (1) another. */
export function shiftMonth({ year, month }: CalendarMonth, months: number): CalendarMonth {
  return monthOf(toDay(new Date(Date.UTC(year, month + months, 1))))
}

/** "October 2026". */
export function monthTitle({ year, month }: CalendarMonth): string {
  return monthFormat.format(new Date(Date.UTC(year, month, 1)))
}

/** The month's days in weeks of seven, Sunday first, with null for the padding around them. */
export function monthGrid({ year, month }: CalendarMonth): (string | null)[][] {
  const count = new Date(Date.UTC(year, month + 1, 0)).getUTCDate()
  const lead = new Date(Date.UTC(year, month, 1)).getUTCDay()
  const cells: (string | null)[] = Array.from({ length: lead }, () => null)
  for (let date = 1; date <= count; date += 1) {
    cells.push(toDay(new Date(Date.UTC(year, month, date))))
  }
  while (cells.length % 7 !== 0) cells.push(null)
  const weeks: (string | null)[][] = []
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7))
  return weeks
}
