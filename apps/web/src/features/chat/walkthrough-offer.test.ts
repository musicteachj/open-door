import { describe, expect, it } from 'vitest'
import { offersWalkthrough } from './walkthrough-offer'

describe('offersWalkthrough', () => {
  it.each(['model-unavailable', 'spend-limit', 'budget-daily'])('offers it for %s', (code) => {
    expect(offersWalkthrough(code)).toBe(true)
  })

  it.each(['budget-sandbox', 'budget-conversation', 'internal', 'refusal', undefined])(
    'does not offer it for %s',
    (code) => {
      expect(offersWalkthrough(code)).toBe(false)
    },
  )
})
