import { describe, expect, it, vi } from 'vitest'
import { todayIn } from './today'

describe('todayIn', () => {
  it('is the date in the zone, which can differ from UTC', () => {
    const lateUtc = new Date('2026-10-27T02:30:00Z')
    expect(todayIn('America/Los_Angeles', lateUtc)).toBe('2026-10-26')
    expect(todayIn('UTC', lateUtc)).toBe('2026-10-27')
    expect(todayIn('Pacific/Auckland', lateUtc)).toBe('2026-10-27')
  })

  it('pads the month and the day', () => {
    expect(todayIn('UTC', new Date('2026-01-05T12:00:00Z'))).toBe('2026-01-05')
  })

  it('builds its date formatter once per zone, not on every call', () => {
    const made = vi.spyOn(Intl, 'DateTimeFormat')
    try {
      todayIn('Asia/Kolkata', new Date('2026-10-27T02:30:00Z'))
      const first = made.mock.calls.length
      todayIn('Asia/Kolkata', new Date('2026-10-28T02:30:00Z'))
      todayIn('Asia/Kolkata', new Date('2026-10-29T02:30:00Z'))
      expect(made.mock.calls.length).toBe(first)
    } finally {
      made.mockRestore()
    }
  })
})
