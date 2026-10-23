import { describe, expect, it } from 'vitest'
import type { DrawOut } from '@/api/generated'
import {
  availableAfter,
  balanceCopy,
  decisionLine,
  failureText,
  foldedScheduleLine,
  formCopy,
  joinList,
  leftLines,
  previewCopy,
  problemText,
  ruleChipLabel,
  ruleChipName,
  skippedLine,
  dayLabel,
  holidayTip,
  pastLabelSick,
  pickerHint,
  statusLabel,
  timeOffCopy,
  typeLabel,
} from './labels'

describe('timeOffCopy', () => {
  it('holds the fixed strings from the screen notes', () => {
    expect(timeOffCopy).toMatchObject({
      typeLabel: 'Type',
      typePto: 'PTO',
      typeSick: 'Sick time',
      datesLabel: 'Dates',
      datesPlaceholder: 'Pick a day or a range',
      howMuchLabel: 'How much',
      fullDay: 'Full day',
      halfDay: 'Half day (4 hours)',
      someHours: 'Some hours',
      hoursLabel: 'Hours',
      hoursHint: '1 to 8 hours',
      hoursError: 'Enter a whole number from 1 to 8.',
      fewerHours: 'Fewer hours',
      moreHours: 'More hours',
      previousMonth: 'Previous month',
      nextMonth: 'Next month',
      done: 'Done',
      legendOff: 'Not on your schedule',
      legendHoliday: 'Company holiday',
      legendToday: 'Today',
      pastLabelPto: 'Past days can’t be picked for PTO',
    })
  })

  it('has no em dash and no pronoun', () => {
    const text = JSON.stringify(timeOffCopy)
    expect(text).not.toContain(String.fromCharCode(0x2014))
    expect(text).not.toMatch(/\b(he|she|him|her|his|hers|they|them|their)\b/i)
  })
})

describe('statusLabel', () => {
  it('has a fixed word for each status', () => {
    expect(statusLabel('waiting')).toBe('Waiting for approval')
    expect(statusLabel('approved')).toBe('Approved')
    expect(statusLabel('denied')).toBe('Denied')
    expect(statusLabel('recorded')).toBe('Recorded')
    expect(statusLabel('canceled')).toBe('Canceled')
  })
})

describe('pastLabelSick', () => {
  it('names the look-back and the earliest day', () => {
    expect(pastLabelSick(30, '2026-09-20')).toBe('Sick time can go back 30 days, to September 20')
  })
})

describe('dayLabel', () => {
  it('is the date alone for an ordinary day', () => {
    expect(dayLabel({ day: '2026-10-21' })).toBe('Wednesday, October 21')
  })

  it('names a holiday', () => {
    expect(dayLabel({ day: '2026-11-26', holiday: 'Thanksgiving' })).toBe(
      'Thursday, November 26, Thanksgiving, company holiday',
    )
  })

  it('says a day is not on the schedule', () => {
    expect(dayLabel({ day: '2026-10-31', off: true })).toBe(
      'Saturday, October 31, not on your schedule',
    )
  })

  it('says today', () => {
    expect(dayLabel({ day: '2026-10-20', today: true })).toBe('Tuesday, October 20, today')
  })

  it('says a day is not available', () => {
    expect(dayLabel({ day: '2026-10-19', disabled: true })).toBe(
      'Monday, October 19, not available',
    )
  })

  it('puts the marks in one order when several apply', () => {
    expect(
      dayLabel({
        day: '2026-11-26',
        holiday: 'Thanksgiving',
        off: true,
        today: true,
        disabled: true,
      }),
    ).toBe(
      'Thursday, November 26, Thanksgiving, company holiday, not on your schedule, today, not available',
    )
  })
})

describe('holidayTip', () => {
  it('is the holiday name with its kind', () => {
    expect(holidayTip('Thanksgiving')).toBe('Thanksgiving, company holiday')
  })
})

describe('pickerHint', () => {
  it('asks for a day before anything is picked', () => {
    expect(pickerHint({})).toBe('Pick a day, or a first and last day.')
  })

  it('asks for the last day while a range is in progress', () => {
    expect(pickerHint({ start: '2026-11-25', inProgress: true })).toBe(
      'Now pick the last day. For one day, choose Done.',
    )
  })

  it('reads back one day or a range', () => {
    expect(pickerHint({ start: '2026-10-30', end: '2026-10-30' })).toBe('Selected: Fri, Oct 30')
    expect(pickerHint({ start: '2026-11-25', end: '2026-11-27' })).toBe(
      'Selected: Wed, Nov 25 to Fri, Nov 27',
    )
    expect(pickerHint({ start: '2026-10-30' })).toBe('Selected: Fri, Oct 30')
  })
})

const EM_DASH = String.fromCharCode(0x2014)
const PRONOUN = /\b(he|she|him|her|his|hers|they|them|their)\b/i

function draw(partial: Partial<DrawOut>): DrawOut {
  return {
    year: null,
    amountMinutes: 480,
    amountLabel: '8 hours (1 day)',
    availableBeforeMinutes: 5520,
    availableBeforeLabel: '92 hours (11.5 days)',
    availableAfterMinutes: 5040,
    availableAfterLabel: '84 hours (10.5 days)',
    ...partial,
  }
}

describe('joinList', () => {
  it('joins with and', () => {
    expect(joinList(['a'])).toBe('a')
    expect(joinList(['a', 'b'])).toBe('a and b')
    expect(joinList(['a', 'b', 'c'])).toBe('a, b, and c')
  })
})

describe('ruleChipLabel and ruleChipName', () => {
  it('puts the section sign before a numeric id only', () => {
    expect(ruleChipLabel({ sectionId: '4.1', title: 'Paid time off' })).toBe(
      'Handbook §4.1 · Paid time off',
    )
    expect(ruleChipLabel({ sectionId: 'CA-4.3', title: 'Sick leave' })).toBe(
      'Handbook CA-4.3 · Sick leave',
    )
  })

  it('names the source for assistive technology', () => {
    expect(ruleChipName({ sectionId: '4.1', title: 'Paid time off' })).toBe(
      'Source: Handbook §4.1, Paid time off',
    )
  })
})

describe('skippedLine', () => {
  it('names a holiday', () => {
    expect(skippedLine({ day: '2026-11-26', reason: 'Thanksgiving' })).toBe(
      'Thursday, November 26 is Thanksgiving, a company holiday',
    )
  })

  it('says a day is not on the schedule', () => {
    expect(skippedLine({ day: '2026-10-31', reason: 'not scheduled' })).toBe(
      'Saturday, October 31 isn’t on your schedule',
    )
  })
})

describe('leftLines', () => {
  it('says what PTO has left after this, from the draw label', () => {
    expect(leftLines('pto', [draw({})])).toEqual(['84 hours (10.5 days) left after this'])
  })

  it('says what sick leave has left this year, in hours only', () => {
    expect(
      leftLines('sick', [draw({ year: 2026, availableAfterLabel: '29 hours (3.625 days)' })]),
    ).toEqual(['29 hours of sick leave left this year'])
  })

  it('names the year when a sick request is in another year than this one', () => {
    expect(
      leftLines('sick', [draw({ year: 2027, availableAfterLabel: '40 hours (5 days)' })], 2026),
    ).toEqual(['40 hours of sick leave left in 2027'])
  })

  it('gives one line per year for a request across New Year', () => {
    expect(
      leftLines('sick', [
        draw({ year: 2026, availableAfterLabel: '16 hours (2 days)' }),
        draw({ year: 2027, availableAfterLabel: '40 hours (5 days)' }),
      ]),
    ).toEqual(['16 hours of sick leave left in 2026', '40 hours of sick leave left in 2027'])
  })
})

describe('problemText', () => {
  const ctx = { type: 'pto' as const, draws: [draw({})], amountLabel: '120 hours (15 days)' }

  it('writes not-enough for PTO from the draw and the amount', () => {
    expect(problemText({ code: 'not-enough', text: 'Fixed.' }, ctx)).toBe(
      'You have 92 hours (11.5 days) available. This request needs 120 hours (15 days).',
    )
  })

  it('writes not-enough for sick leave in hours, from the year that runs short', () => {
    const sick = {
      type: 'sick' as const,
      amountLabel: '40 hours (5 days)',
      draws: [
        draw({
          year: 2026,
          amountLabel: '40 hours (5 days)',
          availableBeforeLabel: '32 hours (4 days)',
        }),
      ],
    }
    expect(problemText({ code: 'not-enough', text: 'Fixed.' }, sick)).toBe(
      'You have 32 hours of sick leave left this year. This request needs 40 hours.',
    )
  })

  it('writes overlaps from the days that clash', () => {
    expect(
      problemText(
        { code: 'overlaps', text: 'Fixed.' },
        { ...ctx, overlappingDays: ['2026-12-23'] },
      ),
    ).toBe('You already have time off on Wednesday, December 23.')
  })

  it('shows the API text for any other code', () => {
    expect(problemText({ code: 'too-long', text: 'That is too long.' }, ctx)).toBe(
      'That is too long.',
    )
  })
})

describe('failureText', () => {
  it('names the clashing days for an overlap', () => {
    expect(failureText({ code: 'overlaps', text: 'x', dates: ['2026-10-30'] }, 'book')).toBe(
      'Couldn’t book this: you already have time off on Friday, October 30. Nothing was changed.',
    )
  })

  it('uses the verb and the API text for any other code', () => {
    expect(failureText({ code: 'status-changed', text: 'That request changed.' }, 'approve')).toBe(
      'Couldn’t approve this. That request changed. Nothing was changed.',
    )
  })
})

describe('decisionLine', () => {
  it('says today, or the day', () => {
    expect(
      decisionLine('approved', '2026-10-20T16:00:00Z', '2026-10-20', 'America/Los_Angeles'),
    ).toBe('Approved today')
    expect(
      decisionLine('denied', '2026-10-05T16:00:00Z', '2026-10-20', 'America/Los_Angeles'),
    ).toBe('Denied October 5')
  })

  it('is null for a request nobody decided', () => {
    expect(decisionLine('approved', null, '2026-10-20', 'UTC')).toBeNull()
  })
})

describe('the preview, form, and balance copy', () => {
  it('holds the fixed strings from the screen notes', () => {
    expect(previewCopy).toMatchObject({
      title: 'What this uses',
      sources: 'Sources',
      empty: 'Pick dates to see what this uses.',
      nothingCounted: 'None of these days are on your schedule, so there’s nothing to request.',
      alreadyBooked: 'Already booked',
    })
    expect(formCopy).toMatchObject({
      title: 'Request time off',
      submitPto: 'Request time off',
      submitSick: 'Record sick time',
      submittingPto: 'Requesting…',
      submittingSick: 'Recording…',
      sickNote: 'Sick time is recorded right away, with no approval.',
      shortNotice: 'More than 3 days usually needs 2 weeks’ notice. You can still request it.',
    })
    expect(formCopy.approverNote('Marcus Bell')).toBe(
      'Marcus Bell, your manager, reviews PTO requests.',
    )
    expect(balanceCopy.ptoLabel).toBe('PTO available')
    expect(balanceCopy.sickLabel).toBe('Sick leave available this year')
  })

  it('has no em dash and no pronoun', () => {
    const text = JSON.stringify([previewCopy, formCopy, balanceCopy, formCopy.approverNote('A B')])
    expect(text).not.toContain(EM_DASH)
    expect(text).not.toMatch(PRONOUN)
  })

  describe('typeLabel and availableAfter', () => {
    it('writes the leave type once, with a lowercase form for the middle of a sentence', () => {
      expect(typeLabel('pto')).toBe('PTO')
      expect(typeLabel('sick')).toBe('Sick time')
      expect(typeLabel('pto', { lower: true })).toBe('PTO')
      expect(typeLabel('sick', { lower: true })).toBe('sick time')
    })

    it('writes the balance line once', () => {
      expect(availableAfter('84 hours (10.5 days)')).toBe(
        '84 hours (10.5 days) available after this',
      )
    })
  })

  describe('foldedScheduleLine', () => {
    it('names the weekdays in week order', () => {
      expect(foldedScheduleLine(['2026-11-10', '2026-11-09'])).toBe(
        'Mondays and Tuesdays in these dates aren’t on your schedule',
      )
      expect(foldedScheduleLine(['2026-11-01', '2026-10-31'])).toBe(
        'Saturdays and Sundays in these dates aren’t on your schedule',
      )
    })
  })
})
