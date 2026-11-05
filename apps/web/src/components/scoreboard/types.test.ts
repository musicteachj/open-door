import { describe, expect, it } from 'vitest'
import generated from '@/generated/scoreboard.json'
import { isScoreboard } from './types'

describe('isScoreboard', () => {
  it('accepts the scoreboard the generator wrote', () => {
    expect(isScoreboard(generated)).toBe(true)
  })

  it('refuses what is not a scoreboard', () => {
    expect(isScoreboard(null)).toBe(false)
    expect(isScoreboard('scoreboard')).toBe(false)
    expect(isScoreboard({})).toBe(false)
  })

  it('refuses a schema it does not know', () => {
    expect(isScoreboard({ ...generated, schema: 2 })).toBe(false)
  })

  it('refuses a set that has lost a field', () => {
    const [first, ...rest] = generated.sets
    expect(isScoreboard({ ...generated, sets: [{ ...first, name: undefined }, ...rest] })).toBe(
      false,
    )
    expect(isScoreboard({ ...generated, sets: [{ ...first, also: 'nope' }, ...rest] })).toBe(false)
    expect(
      isScoreboard({ ...generated, sets: [{ ...first, headline: { label: 1 } }, ...rest] }),
    ).toBe(false)
  })

  it('refuses a history row that has lost a field', () => {
    const [first, ...rest] = generated.history
    expect(isScoreboard({ ...generated, history: [{ ...first, cost: 12 }, ...rest] })).toBe(false)
    expect(isScoreboard({ ...generated, history: [{ ...first, date: undefined }, ...rest] })).toBe(
      false,
    )
  })

  it('refuses facts with a mistyped items count or models', () => {
    const [first, ...rest] = generated.sets
    const withFacts = (facts: unknown) =>
      isScoreboard({ ...generated, sets: [{ ...first, facts }, ...rest] })
    expect(withFacts({ itemsPerTrial: 166 })).toBe(true)
    expect(withFacts({ models: { assistant: 'a', guard: 'g' } })).toBe(true)
    expect(withFacts({ models: null })).toBe(true)
    expect(withFacts({ itemsPerTrial: '166' })).toBe(false)
    expect(withFacts({ models: 'claude-opus-5-5' })).toBe(false)
    expect(withFacts({ models: { assistant: 5 } })).toBe(false)
  })

  it('refuses facts with a mistyped model, trials, or date', () => {
    const [first, ...rest] = generated.sets
    const withFacts = (facts: unknown) =>
      isScoreboard({ ...generated, sets: [{ ...first, facts }, ...rest] })
    expect(withFacts({ model: 'claude-opus-5-5', trials: 3, date: 'Oct 19, 2026' })).toBe(true)
    expect(withFacts({ model: null })).toBe(true)
    expect(withFacts({ model: 5 })).toBe(false)
    expect(withFacts({ trials: '3' })).toBe(false)
    expect(withFacts({ date: 20261019 })).toBe(false)
  })

  it('accepts the nulls the board writer gives an older run that lacks a fact', () => {
    const [first, ...rest] = generated.sets
    const withFacts = (facts: unknown) =>
      isScoreboard({ ...generated, sets: [{ ...first, facts }, ...rest] })
    expect(withFacts({ itemsPerTrial: null, trials: null, date: null, model: null })).toBe(true)
    expect(withFacts({ models: { assistant: 'a', guard: null, judge: null } })).toBe(true)
  })

  it('accepts a set that was not run and a history with no rows', () => {
    const notRun = {
      key: 'x',
      name: 'X',
      detail: null,
      notRun: true,
      headline: null,
      lowest: null,
      also: [],
      facts: null,
    }
    expect(isScoreboard({ schema: 1, sets: [notRun], history: [] })).toBe(true)
  })
})
