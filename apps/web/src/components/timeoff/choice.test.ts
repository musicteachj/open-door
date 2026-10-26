import { describe, expect, it } from 'vitest'
import { howMuchOptionsFor, resolveChoice } from './choice'

describe('howMuchOptionsFor', () => {
  it('offers Full day and Half day for PTO, and Full day and Some hours for sick time', () => {
    expect(howMuchOptionsFor('pto').map((option) => option.value)).toEqual(['full', 'half'])
    expect(howMuchOptionsFor('sick').map((option) => option.value)).toEqual(['full', 'hours'])
  })
})

describe('resolveChoice', () => {
  it('is Full day for a range, whatever was chosen', () => {
    expect(resolveChoice('pto', '2026-11-09', '2026-11-10', 'half', '3')).toEqual({
      howMuch: 'full',
      hours: null,
    })
    expect(resolveChoice('sick', '2026-11-09', '2026-11-10', 'hours', '3')).toEqual({
      howMuch: 'full',
      hours: null,
    })
  })

  it('is Full day when nothing is picked yet', () => {
    expect(resolveChoice('pto', undefined, undefined, 'half', '3')).toEqual({
      howMuch: 'full',
      hours: null,
    })
  })

  it('keeps a half day of PTO on one day, with no hours', () => {
    expect(resolveChoice('pto', '2026-10-30', '2026-10-30', 'half', '3')).toEqual({
      howMuch: 'half',
      hours: null,
    })
  })

  it('is Full day for a how-much the type does not offer', () => {
    expect(resolveChoice('sick', '2026-10-30', '2026-10-30', 'half', '3')).toEqual({
      howMuch: 'full',
      hours: null,
    })
    expect(resolveChoice('pto', '2026-10-30', '2026-10-30', 'hours', '3')).toEqual({
      howMuch: 'full',
      hours: null,
    })
  })

  it('reads the hours for sick time on one day, and null for text that is not 1 to 8', () => {
    expect(resolveChoice('sick', '2026-10-22', '2026-10-22', 'hours', ' 3 ')).toEqual({
      howMuch: 'hours',
      hours: 3,
    })
    expect(resolveChoice('sick', '2026-10-22', '2026-10-22', 'hours', '12')).toEqual({
      howMuch: 'hours',
      hours: null,
    })
  })
})
