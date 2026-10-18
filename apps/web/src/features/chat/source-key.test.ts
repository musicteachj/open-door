import { describe, expect, it } from 'vitest'
import { citation } from '@/test/assistant-fixtures'
import { parseSourceKey, sourceKey, withSourceKeys } from './source-key'

describe('sourceKey', () => {
  it('joins the section and the passage, since the API numbers passages within a section', () => {
    expect(sourceKey('CA-4.3', 'p2')).toBe('CA-4.3~p2')
  })

  it('tells two sections apart that both have a p1', () => {
    expect(sourceKey('CA-4.3', 'p1')).not.toBe(sourceKey('4.3', 'p1'))
  })
})

describe('parseSourceKey', () => {
  it('splits at the first tilde', () => {
    expect(parseSourceKey('CA-4.3~p2')).toEqual({ sectionId: 'CA-4.3', passageId: 'p2' })
  })

  it('refuses a value that is not a section and a passage', () => {
    for (const bad of [null, '', 'p2', '~p2', 'CA-4.3~', '..~p1', 'CA-4.3~..']) {
      expect(parseSourceKey(bad)).toBeNull()
    }
  })
})

describe('withSourceKeys', () => {
  it('makes each citation name its passage with the section too, and only once', () => {
    const once = withSourceKeys([citation({ passageId: 'p2' })])
    expect(once[0]?.passageId).toBe('CA-4.3~p2')
    expect(withSourceKeys(once)).toEqual(once)
  })

  it('returns the same array for the same input, so a memoized render is not defeated', () => {
    const citations = [citation({ passageId: 'p2' })]
    expect(withSourceKeys(citations)).toBe(withSourceKeys(citations))
  })
})
