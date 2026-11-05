import { describe, expect, it } from 'vitest'
import { dayInZone, dateTimeInZone, formatCalendarDate, timeInZone } from './case-dates'

const SENT = '2026-10-26T16:41:00Z' // 10:41 AM in Denver (MDT)

describe('case dates', () => {
  it('shows a calendar date without a time zone shift', () => {
    expect(formatCalendarDate('2026-10-28')).toBe('Wed, Oct 28')
    expect(formatCalendarDate('2026-10-26')).toBe('Mon, Oct 26')
  })

  it('shows a timestamp as a day in the given zone', () => {
    expect(dayInZone(SENT, 'America/Denver')).toBe('Mon, Oct 26')
    // 02:00 UTC on the 27th is still the 26th in Denver, and already the 27th in UTC.
    expect(dayInZone('2026-10-27T02:00:00Z', 'America/Denver')).toBe('Mon, Oct 26')
    expect(dayInZone('2026-10-27T02:00:00Z', 'UTC')).toBe('Tue, Oct 27')
  })

  it('shows the time with the zone abbreviation, with a plain space', () => {
    expect(timeInZone(SENT, 'America/Denver')).toBe('10:41 AM MDT')
    expect(timeInZone(SENT, 'America/Denver')).not.toMatch(/ /)
  })

  it('shows the date and the time together', () => {
    expect(dateTimeInZone(SENT, 'America/Denver')).toBe('Mon, Oct 26, 10:41 AM MDT')
  })
})
