import { describe, expect, it } from 'vitest'
import { afterEdit } from './edit'
import { CASE_LIMIT_CHARACTERS } from './validate'

const LIMIT = CASE_LIMIT_CHARACTERS
// Digits and letters in a repeating pattern with no "Z", so a pasted run of Z is easy to find.
const base = (count: number) => 'abcdefghij'.repeat(Math.ceil(count / 10)).slice(0, count)

describe('afterEdit', () => {
  it('lets an edit within the limit stand', () => {
    expect(afterEdit('abc', 'abcd', 'insertText')).toEqual({ value: 'abcd', caret: null })
  })

  it('lets a deletion stand when the text is still over the limit', () => {
    const over = 'a'.repeat(LIMIT + 5)
    expect(afterEdit(over, over.slice(1), 'deleteContentBackward')?.value).toBe(over.slice(1))
  })

  it('refuses a keystroke past the limit', () => {
    expect(afterEdit(base(LIMIT), `${base(LIMIT)}x`, 'insertText')).toBeNull()
  })

  it('cuts only the pasted part when pasting in the middle, keeping all existing text', () => {
    const previous = base(3990)
    const pasted = 'Z'.repeat(50)
    const next = previous.slice(0, 10) + pasted + previous.slice(10)
    const result = afterEdit(previous, next, 'insertFromPaste')!
    expect([...result.value]).toHaveLength(LIMIT)
    expect(result.value).toBe(previous.slice(0, 10) + 'Z'.repeat(10) + previous.slice(10))
    // The caret lands after the part that was kept.
    expect(result.caret).toBe(20)
  })

  it('cuts a paste at the end the same way', () => {
    const previous = base(3990)
    const result = afterEdit(previous, previous + 'Z'.repeat(50), 'insertFromPaste')!
    expect(result.value).toBe(previous + 'Z'.repeat(10))
    expect(result.caret).toBe(LIMIT)
  })

  it('cuts a paste that replaces a selection, keeping the text around it', () => {
    const previous = base(LIMIT)
    // Select 5 characters at 100 to 105 and paste 20: 15 more than there was room for.
    const next = previous.slice(0, 100) + 'Z'.repeat(20) + previous.slice(105)
    const result = afterEdit(previous, next, 'insertFromPaste')!
    expect([...result.value]).toHaveLength(LIMIT)
    expect(result.value).toBe(previous.slice(0, 100) + 'Z'.repeat(5) + previous.slice(105))
  })

  it('counts code points, so an emoji is never split', () => {
    const previous = base(3998)
    const result = afterEdit(
      previous,
      `${previous.slice(0, 5)}😀😀😀${previous.slice(5)}`,
      'insertFromPaste',
    )!
    expect([...result.value]).toHaveLength(LIMIT)
    expect(result.value).toBe(`${previous.slice(0, 5)}😀😀${previous.slice(5)}`)
    expect(result.caret).toBe(5 + 4)
  })

  it.each(['insertFromDrop', 'insertCompositionText', 'insertReplacementText'])(
    'treats %s like a paste, so an IME or autocorrect is cut, not refused',
    (inputType) => {
      const previous = base(3995)
      const next = previous.slice(0, 50) + 'Z'.repeat(20) + previous.slice(50)
      expect(afterEdit(previous, next, inputType)?.value).toBe(
        previous.slice(0, 50) + 'Z'.repeat(5) + previous.slice(50),
      )
    },
  )

  it('keeps the existing text whole even when nothing is left for the insertion', () => {
    const previous = base(LIMIT)
    const next = previous.slice(0, 7) + 'Z'.repeat(3) + previous.slice(7)
    expect(afterEdit(previous, next, 'insertFromPaste')?.value).toBe(previous)
  })
})
