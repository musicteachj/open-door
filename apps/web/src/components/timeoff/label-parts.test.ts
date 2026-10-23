import { describe, expect, it } from 'vitest'
import { splitLabel } from './label-parts'

describe('splitLabel', () => {
  it('splits hours from days at the parenthesis', () => {
    expect(splitLabel('92 hours (11.5 days)')).toEqual({ hours: '92 hours', days: '11.5 days' })
    expect(splitLabel('8 hours (1 day)')).toEqual({ hours: '8 hours', days: '1 day' })
  })

  it('keeps a word for the days when the label has one', () => {
    expect(splitLabel('4 hours (half a day)')).toEqual({
      hours: '4 hours',
      days: 'half a day',
    })
  })

  it('has hours only when the label has no days part', () => {
    expect(splitLabel('8 hours')).toEqual({ hours: '8 hours' })
    expect(splitLabel('1 hour')).toEqual({ hours: '1 hour' })
  })

  it('leaves hours and minutes as they are', () => {
    expect(splitLabel('1 hour 30 minutes')).toEqual({ hours: '1 hour 30 minutes' })
  })

  it('splits a negative label the same way', () => {
    expect(splitLabel('-8 hours (-1 day)')).toEqual({ hours: '-8 hours', days: '-1 day' })
  })

  it('splits only at the first parenthesis', () => {
    expect(splitLabel('8 hours (1 day) (extra)')).toEqual({
      hours: '8 hours',
      days: '1 day) (extra',
    })
  })

  it('does not split a label whose parenthesis never closes', () => {
    expect(splitLabel('8 hours (1 day')).toEqual({ hours: '8 hours (1 day' })
  })

  it('returns an empty label as hours', () => {
    expect(splitLabel('')).toEqual({ hours: '' })
  })
})
