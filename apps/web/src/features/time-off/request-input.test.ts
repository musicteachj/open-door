import { describe, expect, it } from 'vitest'
import { toPossibleRequest } from './request-input'

describe('toPossibleRequest', () => {
  it('is nothing until a day is picked', () => {
    expect(
      toPossibleRequest('pto', undefined, undefined, { howMuch: 'full', hours: null }, 240),
    ).toBeNull()
  })

  it('sends a full day or a range with no partial amount', () => {
    expect(
      toPossibleRequest('pto', '2026-11-25', '2026-11-27', { howMuch: 'full', hours: null }, 240),
    ).toEqual({ type: 'pto', startDate: '2026-11-25', endDate: '2026-11-27', partialMinutes: null })
  })

  it('sends a PTO half day as the minutes the calendar gives', () => {
    expect(
      toPossibleRequest('pto', '2026-10-30', '2026-10-30', { howMuch: 'half', hours: null }, 240),
    ).toEqual({
      type: 'pto',
      startDate: '2026-10-30',
      endDate: '2026-10-30',
      partialMinutes: 240,
    })
  })

  it('sends the half day the calendar names, whatever it is', () => {
    expect(
      toPossibleRequest('pto', '2026-10-30', '2026-10-30', { howMuch: 'half', hours: null }, 300),
    ).toMatchObject({ partialMinutes: 300 })
  })

  it('sends sick hours as minutes, and nothing for hours that are not a number', () => {
    expect(
      toPossibleRequest('sick', '2026-10-22', '2026-10-22', { howMuch: 'hours', hours: 3 }, 240),
    ).toEqual({
      type: 'sick',
      startDate: '2026-10-22',
      endDate: '2026-10-22',
      partialMinutes: 180,
    })
    expect(
      toPossibleRequest('sick', '2026-10-22', '2026-10-22', { howMuch: 'hours', hours: null }, 240),
    ).toBeNull()
  })
})
