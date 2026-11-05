import { describe, expect, it } from 'vitest'
import { isOutcomeBadge, OUTCOME_BADGE_WORDS, outcomeBadgeFor } from './outcome-badges'

describe('outcome badges', () => {
  it('says each outcome in its own words', () => {
    expect(OUTCOME_BADGE_WORDS).toEqual({
      'outcome-answered': 'Answered',
      'outcome-not-covered': 'Said the handbook doesn’t cover it',
      'outcome-refused': 'Refused by the model',
      'outcome-stopped': 'Stopped by the person',
      'outcome-failed': 'Failed',
      'outcome-cap': 'Spending cap reached',
      'outcome-safety-unavailable': 'Safety check unavailable',
    })
  })

  it.each([
    ['answered', 'outcome-answered'],
    ['not_found', 'outcome-not-covered'],
    ['refused', 'outcome-refused'],
    ['stopped', 'outcome-stopped'],
    ['failed', 'outcome-failed'],
    ['budget', 'outcome-cap'],
    ['guard_unavailable', 'outcome-safety-unavailable'],
  ])('maps the API outcome %s to %s', (outcome, badge) => {
    expect(outcomeBadgeFor(outcome)).toBe(badge)
  })

  it('maps nothing for an outcome it does not know', () => {
    expect(outcomeBadgeFor('mystery')).toBeNull()
    expect(outcomeBadgeFor(null)).toBeNull()
    expect(outcomeBadgeFor('toString')).toBeNull()
  })

  it('tells outcome badges from other values', () => {
    expect(isOutcomeBadge('outcome-failed')).toBe(true)
    expect(isOutcomeBadge('case-new')).toBe(false)
    expect(isOutcomeBadge('toString')).toBe(false)
  })
})
