import { afterEach, describe, expect, it } from 'vitest'
import {
  addDays,
  addMonths,
  calendarDayIn,
  compareDays,
  endOfNextYear,
  firstOfMonth,
  lastOfMonth,
  shiftMonth,
  isoWeekday,
  longDate,
  longRange,
  monthGrid,
  monthDay,
  monthDayRange,
  monthOf,
  monthTitle,
  shortDate,
  shortRange,
} from './dates'

describe('longDate and shortDate', () => {
  it('write the weekday and the day, with no year', () => {
    expect(longDate('2026-10-30')).toBe('Friday, October 30')
    expect(shortDate('2026-10-30')).toBe('Fri, Oct 30')
    expect(longDate('2026-12-23')).toBe('Wednesday, December 23')
    expect(shortDate('2026-11-05')).toBe('Thu, Nov 5')
  })

  it('handle the ends of the year and a leap day', () => {
    expect(longDate('2026-12-31')).toBe('Thursday, December 31')
    expect(shortDate('2027-01-01')).toBe('Fri, Jan 1')
    expect(longDate('2028-02-29')).toBe('Tuesday, February 29')
  })
})

describe('monthDay', () => {
  it('writes the month in full and the day, for a sentence', () => {
    expect(monthDay('2026-09-20')).toBe('September 20')
    expect(monthDay('2027-01-05')).toBe('January 5')
  })
})

describe('ranges', () => {
  it('join the two ends with "to"', () => {
    expect(longRange('2026-11-25', '2026-11-27')).toBe(
      'Wednesday, November 25 to Friday, November 27',
    )
    expect(shortRange('2026-11-25', '2026-11-27')).toBe('Wed, Nov 25 to Fri, Nov 27')
  })

  it('read as one day when the start is the end', () => {
    expect(longRange('2026-10-30', '2026-10-30')).toBe('Friday, October 30')
    expect(shortRange('2026-10-30', '2026-10-30')).toBe('Fri, Oct 30')
  })
})

describe('isoWeekday', () => {
  it('is 1 for Monday through 7 for Sunday', () => {
    expect(isoWeekday('2026-10-19')).toBe(1)
    expect(isoWeekday('2026-10-23')).toBe(5)
    expect(isoWeekday('2026-10-24')).toBe(6)
    expect(isoWeekday('2026-10-25')).toBe(7)
  })
})

describe('addDays', () => {
  it('moves across months and years, forward and back', () => {
    expect(addDays('2026-10-31', 1)).toBe('2026-11-01')
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01')
    expect(addDays('2026-10-20', -30)).toBe('2026-09-20')
    expect(addDays('2026-10-20', 0)).toBe('2026-10-20')
    expect(addDays('2026-10-20', 7)).toBe('2026-10-27')
  })

  it('does not slip an hour across a daylight saving change', () => {
    expect(addDays('2026-11-01', 1)).toBe('2026-11-02')
    expect(addDays('2026-03-08', 1)).toBe('2026-03-09')
    expect(addDays('2026-11-02', -1)).toBe('2026-11-01')
  })
})

describe('addMonths', () => {
  it('keeps the date when the month has it', () => {
    expect(addMonths('2026-10-20', 1)).toBe('2026-11-20')
    expect(addMonths('2026-10-20', -1)).toBe('2026-09-20')
    expect(addMonths('2026-12-15', 1)).toBe('2027-01-15')
    expect(addMonths('2026-01-15', -1)).toBe('2025-12-15')
  })

  it('clamps to the end of a shorter month', () => {
    expect(addMonths('2026-10-31', 1)).toBe('2026-11-30')
    expect(addMonths('2026-03-31', -1)).toBe('2026-02-28')
    expect(addMonths('2028-01-31', 1)).toBe('2028-02-29')
    expect(addMonths('2026-10-31', -1)).toBe('2026-09-30')
  })
})

describe('compareDays', () => {
  it('orders by calendar date', () => {
    expect(compareDays('2026-10-20', '2026-10-21')).toBeLessThan(0)
    expect(compareDays('2026-11-01', '2026-10-31')).toBeGreaterThan(0)
    expect(compareDays('2026-10-20', '2026-10-20')).toBe(0)
    expect(compareDays('2027-01-01', '2026-12-31')).toBeGreaterThan(0)
  })
})

describe('monthOf and monthTitle', () => {
  it('give the year and the zero-based month, and the title', () => {
    expect(monthOf('2026-10-20')).toEqual({ year: 2026, month: 9 })
    expect(monthTitle({ year: 2026, month: 9 })).toBe('October 2026')
    expect(monthTitle({ year: 2027, month: 0 })).toBe('January 2027')
  })
})

describe('firstOfMonth, lastOfMonth, and shiftMonth', () => {
  it('give the ends of a month as days', () => {
    expect(firstOfMonth({ year: 2026, month: 9 })).toBe('2026-10-01')
    expect(lastOfMonth({ year: 2026, month: 9 })).toBe('2026-10-31')
    expect(lastOfMonth({ year: 2026, month: 1 })).toBe('2026-02-28')
    expect(lastOfMonth({ year: 2028, month: 1 })).toBe('2028-02-29')
  })

  it('step a month across the year', () => {
    expect(shiftMonth({ year: 2026, month: 11 }, 1)).toEqual({ year: 2027, month: 0 })
    expect(shiftMonth({ year: 2026, month: 0 }, -1)).toEqual({ year: 2025, month: 11 })
    expect(shiftMonth({ year: 2026, month: 9 }, 0)).toEqual({ year: 2026, month: 9 })
  })
})

describe('monthGrid', () => {
  it('lays out October 2026 in weeks that start on Sunday, padded with nulls', () => {
    const weeks = monthGrid({ year: 2026, month: 9 })
    expect(weeks.every((week) => week.length === 7)).toBe(true)
    // October 1, 2026 is a Thursday.
    expect(weeks[0]).toEqual([null, null, null, null, '2026-10-01', '2026-10-02', '2026-10-03'])
    expect(weeks.at(-1)).toEqual([
      '2026-10-25',
      '2026-10-26',
      '2026-10-27',
      '2026-10-28',
      '2026-10-29',
      '2026-10-30',
      '2026-10-31',
    ])
    expect(weeks).toHaveLength(5)
    expect(weeks.flat().filter((day) => day !== null)).toHaveLength(31)
  })

  it('starts the first row on Sunday when the month does', () => {
    // February 2026 starts on a Sunday and has 28 days: four full weeks.
    const weeks = monthGrid({ year: 2026, month: 1 })
    expect(weeks).toHaveLength(4)
    expect(weeks[0]?.[0]).toBe('2026-02-01')
    expect(weeks.flat().every((day) => day !== null)).toBe(true)
  })

  it('needs six rows when a long month starts late in the week', () => {
    // August 2026 starts on a Saturday and has 31 days.
    const weeks = monthGrid({ year: 2026, month: 7 })
    expect(weeks).toHaveLength(6)
    expect(weeks[0]?.slice(0, 6)).toEqual([null, null, null, null, null, null])
    expect(weeks[0]?.[6]).toBe('2026-08-01')
  })
})

describe('in a time zone behind UTC', () => {
  const original = process.env.TZ
  afterEach(() => {
    if (original === undefined) delete process.env.TZ
    else process.env.TZ = original
  })

  it('gives the same dates, where a plain Date would be a day early', () => {
    process.env.TZ = 'America/Los_Angeles'
    // The proof the zone really changed: a naive parse of a date-only string is UTC midnight,
    // which is the evening of October 22 in Los Angeles.
    const naive = new Date('2026-10-23').toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
    })
    expect(naive).toBe('October 22')

    expect(longDate('2026-10-23')).toBe('Friday, October 23')
    expect(shortDate('2026-10-23')).toBe('Fri, Oct 23')
    expect(isoWeekday('2026-10-23')).toBe(5)
    expect(addDays('2026-10-23', 1)).toBe('2026-10-24')
    expect(addDays('2026-11-01', 1)).toBe('2026-11-02')
    expect(addMonths('2026-10-31', 1)).toBe('2026-11-30')
    expect(monthGrid({ year: 2026, month: 9 })[0]?.[4]).toBe('2026-10-01')
    expect(longRange('2026-11-25', '2026-11-27')).toBe(
      'Wednesday, November 25 to Friday, November 27',
    )
  })
})

describe('monthDayRange', () => {
  it('writes one day, a range in one month, and a range across months', () => {
    expect(monthDayRange('2026-10-30', '2026-10-30')).toBe('October 30')
    expect(monthDayRange('2026-11-09', '2026-11-10')).toBe('November 9 to 10')
    expect(monthDayRange('2026-11-30', '2026-12-02')).toBe('November 30 to December 2')
  })
})

describe('calendarDayIn', () => {
  it('gives the calendar day in a time zone, not in UTC', () => {
    // 03:00 UTC on the 21st is still the evening of the 20th in Oakland.
    expect(calendarDayIn('2026-10-21T03:00:00Z', 'America/Los_Angeles')).toBe('2026-10-20')
    expect(calendarDayIn('2026-10-21T03:00:00Z', 'UTC')).toBe('2026-10-21')
  })
})

describe('endOfNextYear', () => {
  it('is December 31 of the year after the date, the last day a request can reach', () => {
    expect(endOfNextYear('2026-10-20')).toBe('2027-12-31')
    expect(endOfNextYear('2026-12-31')).toBe('2027-12-31')
    expect(endOfNextYear('2027-01-01')).toBe('2028-12-31')
  })
})
