import { describe, expect, it } from 'vitest'
import { CASE_LIMIT_CHARACTERS, characterCountOf, validateCase } from './validate'

const OK = 'My manager keeps making comments about my age.'

describe('validateCase', () => {
  it('passes a category and ordinary words', () => {
    expect(validateCase({ category: 'pay', text: OK })).toEqual([])
  })

  it('flags a missing category first, and then empty words, together', () => {
    expect(validateCase({ category: null, text: '' })).toEqual(['category', 'empty'])
  })

  it('counts whitespace-only words as empty, as the server does', () => {
    expect(validateCase({ category: 'pay', text: ' \n\t  ' })).toEqual(['empty'])
    // Python's strip() also trims U+001C to U+001F and U+0085.
    expect(validateCase({ category: 'pay', text: '\u001c\u0085' })).toEqual(['empty'])
  })

  it('flags a Social Security or card number after the category and before the limit', () => {
    expect(validateCase({ category: null, text: `${OK} My number is 123-45-6789.` })).toEqual([
      'category',
      'personal-data',
    ])
    expect(
      validateCase({ category: 'pay', text: 'Card 4242 4242 4242 4242 was charged.' }),
    ).toEqual(['personal-data'])
  })

  it('flags the limit last, at exactly 4,000 characters, which the server would accept', () => {
    const atLimit = 'a'.repeat(CASE_LIMIT_CHARACTERS)
    expect(validateCase({ category: 'pay', text: atLimit })).toEqual(['limit'])
    expect(validateCase({ category: 'pay', text: atLimit.slice(1) })).toEqual([])
    expect(validateCase({ category: null, text: atLimit })).toEqual(['category', 'limit'])
  })

  it('lists personal data before the limit when both apply', () => {
    const text = `123-45-6789 ${'a'.repeat(CASE_LIMIT_CHARACTERS)}`.slice(0, CASE_LIMIT_CHARACTERS)
    expect(validateCase({ category: 'pay', text })).toEqual(['personal-data', 'limit'])
  })

  it('never lists empty and personal data together', () => {
    expect(validateCase({ category: 'pay', text: '' })).toEqual(['empty'])
  })
})

describe('characterCountOf', () => {
  it('counts code points, as the server does, so an emoji is one', () => {
    expect(characterCountOf('a😀b')).toBe(3)
    expect('a😀b'.length).toBe(4)
  })

  it('does not trim: the server counts the words as sent', () => {
    expect(characterCountOf('  a  ')).toBe(5)
  })
})
