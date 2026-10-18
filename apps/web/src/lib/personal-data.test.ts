import { describe, expect, it } from 'vitest'
// The shared vectors live outside apps/web: the API's test reads the same file, so the two checks
// cannot drift. Never copy it.
import cases from '../../../../evals/assistant/personal-data-cases.json'
import { kindOfPersonalData, normalized } from './personal-data'

describe('the shared vectors', () => {
  it('are present', () => {
    expect(cases.caught.length).toBeGreaterThanOrEqual(10)
    expect(cases.passes.length).toBeGreaterThanOrEqual(10)
    for (const entry of [...cases.caught, ...cases.passes]) {
      expect(Object.keys(entry).sort()).toEqual(['text', 'why'])
    }
  })

  it.each(cases.caught.map((entry) => [entry.why, entry.text]))('catches %s', (_why, text) => {
    expect(kindOfPersonalData(text!)).not.toBeNull()
  })

  it.each(cases.passes.map((entry) => [entry.why || 'empty', entry.text]))(
    'passes %s',
    (_why, text) => {
      expect(kindOfPersonalData(text!)).toBeNull()
    },
  )
})

describe('kindOfPersonalData', () => {
  it('reports the kind', () => {
    expect(kindOfPersonalData('123-45-6789')).toBe('ssn')
    expect(kindOfPersonalData('4111 1111 1111 1111')).toBe('card')
  })

  it('reports a Social Security number when the text holds both', () => {
    expect(kindOfPersonalData('4111111111111111 and 123-45-6789')).toBe('ssn')
  })

  it('does not flag a card-length number that fails the Luhn check', () => {
    expect(kindOfPersonalData('4111111111111112')).toBeNull()
  })

  it('does not flag two dates that run together', () => {
    expect(kindOfPersonalData('2026-10-19 2026-10-23')).toBeNull()
  })

  it('does not flag a Social Security shape inside a longer digit run', () => {
    expect(kindOfPersonalData('123-45-67890')).toBeNull()
    expect(kindOfPersonalData('1123-45-6789')).toBeNull()
  })

  it('reads a space separator that NFKC leaves alone (U+1680) as a space', () => {
    expect(kindOfPersonalData('123\u168045\u16806789')).toBe('ssn')
  })

  it('does not flag a grouped number of 12 or 20 digits, even when it passes the Luhn check', () => {
    expect(kindOfPersonalData('4111 0000 0008')).toBeNull()
    expect(kindOfPersonalData('4111 0000 0000 0000 0008')).toBeNull()
  })

  it('reads full-width digits and odd dashes as the ASCII ones', () => {
    expect(kindOfPersonalData('１２３‑４５‑６７８９')).toBe('ssn')
  })
})

describe('normalized', () => {
  it('drops format characters, maps spaces and dashes to ASCII, and applies NFKC', () => {
    expect(normalized('1​2 3–4５')).toBe('12 3-45')
  })
})
