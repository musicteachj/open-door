import { describe, expect, it } from 'vitest'
import { Category } from '@/api/generated'
import {
  CATEGORY_OPTIONS,
  caseCopy,
  categoryLabel,
  countLine,
  hrBadge,
  personBadge,
} from './labels'

describe('case labels', () => {
  it('labels every category the API knows, in the design’s order', () => {
    expect(CATEGORY_OPTIONS.map((option) => option.value)).toEqual([
      'harassment_discrimination',
      'safety',
      'medical_accommodation',
      'pay',
      'other',
    ])
    expect(new Set(CATEGORY_OPTIONS.map((o) => o.value))).toEqual(new Set(Object.values(Category)))
    expect(categoryLabel('other')).toBe('Something else, or not sure')
  })

  it('says the count against the limit, with the Shorten-it line at the limit', () => {
    expect(countLine(46)).toBe('46 of 4,000 characters')
    expect(countLine(0)).toBe('0 of 4,000 characters')
    expect(countLine(3999)).toBe('3,999 of 4,000 characters')
    expect(countLine(4000)).toBe('4,000 of 4,000 characters. Shorten it to send.')
  })

  it('maps a status to each audience’s badge', () => {
    expect(personBadge('new')).toBe('case-sent')
    expect(personBadge('in_review')).toBe('case-reviewing')
    expect(personBadge('closed')).toBe('case-finished')
    expect(hrBadge('new')).toBe('case-new')
    expect(hrBadge('in_review')).toBe('case-in-review')
    expect(hrBadge('closed')).toBe('case-closed')
  })

  it('has no em dash in any copy', () => {
    const all = JSON.stringify([caseCopy, CATEGORY_OPTIONS])
    expect(all).not.toContain(String.fromCharCode(0x2014))
  })
})
