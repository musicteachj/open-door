import { describe, expect, it } from 'vitest'
import { formatShortDate, formatTimeLeft, greetingFor, greetingLine, isExpiringSoon } from './time'

const MIN = 60_000
const HOUR = 60 * MIN

describe('formatTimeLeft', () => {
  it.each([
    ['24 h', 24 * HOUR, '24 h'],
    ['21 h 59 min rounds down', 21 * HOUR + 59 * MIN, '21 h'],
    ['21 h', 21 * HOUR, '21 h'],
    ['3 h exactly', 3 * HOUR, '3 h'],
    ['3 h and 1 ms', 3 * HOUR + 1, '3 h'],
    ['2 h 59 min 59 s', 3 * HOUR - 1000, '2 h 59 min'],
    ['2 h 50 min', 2 * HOUR + 50 * MIN, '2 h 50 min'],
    ['2 h 0 min is whole hours', 2 * HOUR, '2 h'],
    ['1 h 5 min', HOUR + 5 * MIN, '1 h 5 min'],
    ['1 h', HOUR, '1 h'],
    ['59 min 59 s', HOUR - 1000, '59 min'],
    ['45 min', 45 * MIN, '45 min'],
    ['1 min', MIN, '1 min'],
    ['30 s is under a minute', 30_000, 'less than a minute'],
    ['0', 0, 'less than a minute'],
    ['negative', -5 * MIN, 'less than a minute'],
    ['NaN, from a bad date', NaN, 'less than a minute'],
    ['Infinity', Infinity, 'less than a minute'],
  ])('%s', (_name, ms, expected) => {
    expect(formatTimeLeft(ms)).toBe(expected)
  })
})

describe('isExpiringSoon', () => {
  it.each([
    [24 * HOUR, false],
    [3 * HOUR + 1, false],
    [3 * HOUR, true],
    [2 * HOUR + 50 * MIN, true],
    [0, true],
    [-1, true],
    [NaN, false],
  ])('%d ms is %s', (ms, expected) => {
    expect(isExpiringSoon(ms)).toBe(expected)
  })
})

describe('greetingFor', () => {
  // October: Los Angeles is UTC-7 (PDT), Chicago UTC-5 (CDT), Denver UTC-6 (MDT).
  it.each([
    ['04:59 is evening', '2026-10-06T11:59:00Z', 'America/Los_Angeles', 'Good evening'],
    ['05:00 is morning', '2026-10-06T12:00:00Z', 'America/Los_Angeles', 'Good morning'],
    ['11:59 is morning', '2026-10-06T18:59:00Z', 'America/Los_Angeles', 'Good morning'],
    ['12:00 is afternoon', '2026-10-06T19:00:00Z', 'America/Los_Angeles', 'Good afternoon'],
    ['16:59 is afternoon', '2026-10-06T23:59:00Z', 'America/Los_Angeles', 'Good afternoon'],
    ['17:00 is evening', '2026-10-07T00:00:00Z', 'America/Los_Angeles', 'Good evening'],
    ['midnight is evening', '2026-10-06T07:00:00Z', 'America/Los_Angeles', 'Good evening'],
    // UTC says 12:30 (afternoon); Oakland says 05:30 (morning).
    [
      'Oakland morning while UTC is afternoon',
      '2026-10-06T12:30:00Z',
      'America/Los_Angeles',
      'Good morning',
    ],
    // UTC says 17:30 (evening); Austin says 12:30 (afternoon).
    [
      'Austin afternoon while UTC is evening',
      '2026-10-06T17:30:00Z',
      'America/Chicago',
      'Good afternoon',
    ],
    ['Denver morning', '2026-10-06T15:00:00Z', 'America/Denver', 'Good morning'],
    [
      'follows the end of daylight time',
      '2026-11-02T13:00:00Z',
      'America/Los_Angeles',
      'Good morning',
    ],
  ])('%s', (_name, iso, timeZone, expected) => {
    expect(greetingFor(new Date(iso), timeZone)).toBe(expected)
  })
})

describe('greetingLine', () => {
  it('addresses the person by first name, with a period', () => {
    expect(greetingLine(new Date('2026-10-06T15:00:00Z'), 'America/Los_Angeles', 'Priya')).toBe(
      'Good morning, Priya.',
    )
  })
})

describe('formatShortDate', () => {
  it.each([
    ['2026-09-12', 'Sep 12, 2026'],
    ['2026-01-01', 'Jan 1, 2026'],
    ['2026-12-31', 'Dec 31, 2026'],
  ])('%s is %s, a calendar date no timezone moves', (iso, expected) => {
    expect(formatShortDate(iso)).toBe(expected)
  })

  it('returns text that is not a date unchanged', () => {
    expect(formatShortDate('soon')).toBe('soon')
  })
})
