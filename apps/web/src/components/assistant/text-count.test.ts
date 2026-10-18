import { describe, expect, it } from 'vitest'
import { characterCount, trimLikePython } from './text-count'

// Every character Python's str.isspace() accepts, and so str.strip() removes, listed by running
// `[hex(c) for c in range(0x110000) if chr(c).isspace()]` on 2026-10-17.
const PYTHON_SPACE = [
  0x9, 0xa, 0xb, 0xc, 0xd, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x85, 0xa0, 0x1680, 0x2000, 0x2001, 0x2002,
  0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200a, 0x2028, 0x2029, 0x202f, 0x205f,
  0x3000,
]

describe('trimLikePython', () => {
  it.each(PYTHON_SPACE)('strips code point %d from both ends', (code) => {
    const space = String.fromCodePoint(code)
    expect(trimLikePython(`${space}${space}word${space}`)).toBe('word')
  })

  it('strips U+001F and U+0085, which JavaScript trim() keeps', () => {
    expect(trimLikePython('\u001fword\u0085')).toBe('word')
    expect('\u001fword\u0085'.trim()).not.toBe('word')
  })

  it('keeps U+FEFF, which JavaScript trim() strips', () => {
    expect(trimLikePython('﻿word')).toBe('﻿word')
  })

  it('keeps zero-width space and the soft hyphen, which Python does not strip either', () => {
    expect(trimLikePython('​word­')).toBe('​word­')
  })

  it('leaves space inside the text, and handles all-space and empty text', () => {
    expect(trimLikePython('  a  b  ')).toBe('a  b')
    expect(trimLikePython(' \u001f \n')).toBe('')
    expect(trimLikePython('')).toBe('')
  })
})

describe('characterCount', () => {
  it('counts code points of the trimmed text, as Python len() does', () => {
    expect(characterCount('  ok 👍 ')).toBe(4)
  })

  it('counts a leading U+FEFF and not a leading U+001F', () => {
    expect(characterCount(`﻿${'a'.repeat(2000)}`)).toBe(2001)
    expect(characterCount(`\u001f${'a'.repeat(2000)}`)).toBe(2000)
  })
})
