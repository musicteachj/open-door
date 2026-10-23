import { describe, expect, it } from 'vitest'
import { parseHours, wholeNumber } from './parse-hours'

describe('parseHours', () => {
  it('reads a whole number from 1 to 8, ignoring spaces and a leading zero', () => {
    expect(parseHours('4')).toBe(4)
    expect(parseHours('08')).toBe(8)
    expect(parseHours(' 4 ')).toBe(4)
  })

  it('gives null for anything else', () => {
    for (const value of ['', '0', '9', '-1', '3.5', 'ab', '4 5', '1e1']) {
      expect({ value, hours: parseHours(value) }).toEqual({ value, hours: null })
    }
  })

  describe('wholeNumber', () => {
    it('reads a whole number with spaces around it, of any size', () => {
      expect(wholeNumber(' 12 ')).toBe(12)
      expect(wholeNumber('08')).toBe(8)
    })

    it('is null for anything else', () => {
      expect(wholeNumber('')).toBeNull()
      expect(wholeNumber('3.5')).toBeNull()
      expect(wholeNumber('-2')).toBeNull()
      expect(wholeNumber('abc')).toBeNull()
    })
  })
})
