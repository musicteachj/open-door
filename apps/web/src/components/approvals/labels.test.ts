import { describe, expect, it } from 'vitest'
import type { CoverageOut } from '@/api/generated'
import { ZARA, ZARA_WAITING } from '@/app/gallery/fixtures/timeoff'
import {
  actionName,
  NOTE_LIMIT_CHARACTERS,
  approvalsCopy,
  conflictText,
  coverageLines,
  decisionFacts,
  firstNameOf,
  sentLine,
} from './labels'

const VIKRAM: CoverageOut = {
  person: { id: 'v', name: 'Vikram Morales' },
  days: [{ date: '2026-11-10', type: 'pto', partialMinutes: null }],
}

describe('coverageLines', () => {
  it('says no one else is off, for a day and for a range', () => {
    expect(coverageLines([], false)).toEqual(['No one else on your team is off that day.'])
    expect(coverageLines([], true)).toEqual(['No one else on your team is off those days.'])
  })

  it('names a colleague, the day, and the type', () => {
    expect(coverageLines([VIKRAM], false)).toEqual([
      'Also off: Vikram Morales, Tuesday, November 10 · PTO',
    ])
  })

  it('joins several days of one type', () => {
    const several: CoverageOut = {
      ...VIKRAM,
      days: [
        { date: '2026-11-09', type: 'pto', partialMinutes: null },
        { date: '2026-11-10', type: 'pto', partialMinutes: null },
      ],
    }
    expect(coverageLines([several], true)).toEqual([
      'Also off: Vikram Morales, Monday, November 9 and Tuesday, November 10 · PTO',
    ])
  })

  it('notes a part of a day without working out hours', () => {
    const partial: CoverageOut = {
      ...VIKRAM,
      days: [{ date: '2026-11-10', type: 'sick', partialMinutes: 180 }],
    }
    expect(coverageLines([partial], false)).toEqual([
      'Also off: Vikram Morales, Tuesday, November 10 (part of the day) · Sick time',
    ])
  })

  it('gives a colleague with two types one line, naming each type', () => {
    const mixed: CoverageOut = {
      ...VIKRAM,
      days: [
        { date: '2026-11-09', type: 'pto', partialMinutes: null },
        { date: '2026-11-10', type: 'sick', partialMinutes: null },
      ],
    }
    expect(coverageLines([mixed], true)).toEqual([
      'Also off: Vikram Morales, Monday, November 9 · PTO, and Tuesday, November 10 · Sick time',
    ])
  })

  it('gives one line per colleague', () => {
    const malik: CoverageOut = { ...VIKRAM, person: { id: 'm', name: 'Malik Flores' } }
    expect(coverageLines([VIKRAM, malik], false)).toHaveLength(2)
  })
})

describe('sentLine', () => {
  it('says today, or the day in the location’s time zone', () => {
    expect(sentLine('2026-10-20T16:00:00Z', '2026-10-20', 'America/Los_Angeles')).toBe('Sent today')
    expect(sentLine('2026-10-17T18:00:00Z', '2026-10-20', 'America/Los_Angeles')).toBe(
      'Sent October 17',
    )
  })
})

describe('actionName', () => {
  it('names Approve and Deny for the request, with the short dates', () => {
    expect(actionName('approve', ZARA, '2026-11-09', '2026-11-10')).toBe(
      'Approve Zara Bautista’s PTO, November 9 to 10',
    )
    expect(actionName('deny', { name: 'Priya Raman' }, '2026-10-30', '2026-10-30')).toBe(
      'Deny Priya Raman’s PTO, October 30',
    )
  })
})

describe('conflictText', () => {
  it('names the person for a canceled request', () => {
    expect(conflictText('canceled', 'Zara')).toBe('Zara canceled this request.')
  })

  it('says a decided request was already decided', () => {
    expect(conflictText('approved', 'Zara')).toBe('This request was already approved.')
    expect(conflictText('denied', 'Zara')).toBe('This request was already denied.')
  })
})

describe('decisionFacts and firstNameOf', () => {
  it('writes the dates and the amount label for a dialog', () => {
    expect(decisionFacts(ZARA_WAITING)).toBe(
      'Monday, November 9 to Tuesday, November 10, 16 hours (2 days).',
    )
  })

  it('takes the first word as the first name', () => {
    expect(firstNameOf('Zara Bautista')).toBe('Zara')
  })
})

describe('approvalsCopy', () => {
  it('has no em dash and no pronoun', () => {
    const text = JSON.stringify(approvalsCopy)
    expect(text).not.toContain(String.fromCharCode(0x2014))
    expect(text).not.toMatch(/\b(he|she|him|her|his|hers|they|them|their)\b/i)
  })

  describe('noteHelper', () => {
    it('names the limit from the constant', () => {
      expect(approvalsCopy.noteHelper('Zara')).toBe(
        `Zara will see this note. Up to ${NOTE_LIMIT_CHARACTERS} characters.`,
      )
    })
  })

  describe('firstNameOf, with spaces around the name', () => {
    it('trims first, so a leading no-break space gives no empty first name', () => {
      expect(firstNameOf('\u00a0Zara Bautista')).toBe('Zara')
      expect(firstNameOf('  Zara  Bautista ')).toBe('Zara')
    })
  })
})
