import { describe, expect, it } from 'vitest'
import { isCaseBadge } from './case-badges'

describe('isCaseBadge', () => {
  it('knows the six badges', () => {
    for (const value of ['case-sent', 'case-new', 'case-closed'])
      expect(isCaseBadge(value)).toBe(true)
  })

  it('does not take inherited object keys for badges', () => {
    for (const value of ['toString', 'constructor', '__proto__', 'hasOwnProperty', 'waiting']) {
      expect(isCaseBadge(value)).toBe(false)
    }
  })
})
