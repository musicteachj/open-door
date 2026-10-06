import { describe, expect, it } from 'vitest'
import { initialsOf } from './initials'

describe('initialsOf', () => {
  it('takes the first letter of the first two words, in capitals', () => {
    expect(initialsOf('Priya Raman')).toBe('PR')
    expect(initialsOf('marcus bell')).toBe('MB')
  })

  it('uses only two letters for a longer name', () => {
    expect(initialsOf('Ana Maria Lopez')).toBe('AM')
  })

  it('keeps a whole character that is outside the basic plane', () => {
    expect(initialsOf('𝒜da Lovelace')).toBe('𝒜L')
    expect(initialsOf('😀 Smile')).toBe('😀S')
  })

  it('handles one word and stray spaces', () => {
    expect(initialsOf('Dana')).toBe('D')
    expect(initialsOf('  Dana   Ortiz ')).toBe('DO')
    expect(initialsOf('')).toBe('')
  })
})
