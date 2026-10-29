import { describe, expect, it } from 'vitest'
import {
  dayInZone,
  dateTimeInZone,
  formatCalendarDate,
  modelDisplayName,
  timeInZone,
} from './case-dates'

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

  it('names a Claude model, and falls back to the raw id', () => {
    expect(modelDisplayName('claude-opus-5-5')).toBe('Claude Opus 5.5')
    expect(modelDisplayName('claude-sonnet-5-5')).toBe('Claude Sonnet 5.5')
    expect(modelDisplayName('claude-haiku-5-5')).toBe('Claude Haiku 5.5')
    expect(modelDisplayName('claude-opus-5-5-20261001')).toBe('Claude Opus 5.5')
    expect(modelDisplayName('claude-sonnet-4-20250514')).toBe('Claude Sonnet 4')
    expect(modelDisplayName('claude-opus-5')).toBe('Claude Opus 5')
    expect(modelDisplayName('claude-opus-4-1-20250805')).toBe('Claude Opus 4.1')
    expect(modelDisplayName('claude-3-5-sonnet')).toBe('claude-3-5-sonnet')
    expect(modelDisplayName('some-other-model')).toBe('some-other-model')
  })
})
