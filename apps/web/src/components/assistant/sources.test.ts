import { describe, expect, it } from 'vitest'
import { apiCitations, citation } from '@/test/assistant-fixtures'
import { distinctSources, numberBySection } from './sources'

const ca1 = citation({ marker: 1, passageId: 'CA-4.3~p1' })
const ca2 = citation({ marker: 1, passageId: 'CA-4.3~p2', offsetUtf16: 40 })
const co = citation({
  marker: 2,
  sectionId: '4.3',
  passageId: '4.3~p3',
  groupName: 'Company handbook',
  title: 'Sick leave',
})

describe('numberBySection', () => {
  it('gives every passage of a section the same number, from the API per-passage numbers', () => {
    const numbered = numberBySection(apiCitations())
    expect(numbered.map((c) => [c.sectionId, c.passageId, c.marker])).toEqual([
      ['CA-4.3', 'CA-4.3~p1', 1],
      ['CA-4.3', 'CA-4.3~p1', 1],
      ['CA-4.3', 'CA-4.3~p2', 1],
      ['4.3', '4.3~p3', 2],
    ])
  })

  it('numbers sections in the order each first appears, not by the API marker', () => {
    const numbered = numberBySection([
      citation({ marker: 5, sectionId: '4.3', passageId: '4.3~p3' }),
      citation({ marker: 2, sectionId: 'CA-4.3' }),
      citation({ marker: 9, sectionId: '4.3', passageId: '4.3~p4' }),
    ])
    expect(numbered.map((c) => c.marker)).toEqual([1, 2, 1])
  })

  it('numbers by where each section first appears in the text, whatever the array order', () => {
    const input = [
      citation({ sectionId: '4.3', passageId: '4.3~p3', offsetUtf16: 50 }),
      citation({ sectionId: 'CA-4.3', offsetUtf16: 10 }),
      citation({ sectionId: '4.3', passageId: '4.3~p4', offsetUtf16: 70 }),
    ]
    const numbered = numberBySection(input)
    // Returned in the array's own order, with the numbers the text order gives.
    expect(numbered.map((c) => [c.sectionId, c.marker])).toEqual([
      ['4.3', 2],
      ['CA-4.3', 1],
      ['4.3', 2],
    ])
  })

  it('lets array order break a tie between citations at the same offset', () => {
    const numbered = numberBySection([
      citation({ sectionId: '4.3', passageId: '4.3~p3', offsetUtf16: 20 }),
      citation({ sectionId: 'CA-4.3', offsetUtf16: 20 }),
    ])
    expect(numbered.map((c) => c.marker)).toEqual([1, 2])
  })

  it('keeps every other field, the order, and the passage each one cites', () => {
    const input = apiCitations()
    const numbered = numberBySection(input)
    expect(numbered).toHaveLength(input.length)
    numbered.forEach((c, i) => expect({ ...c, marker: 0 }).toEqual({ ...input[i], marker: 0 }))
  })

  it('does not change what it was given', () => {
    const input = apiCitations()
    numberBySection(input)
    expect(input.map((c) => c.marker)).toEqual([1, 1, 2, 3])
  })

  it('gives the same result when applied again', () => {
    const once = numberBySection(apiCitations())
    expect(numberBySection(once)).toEqual(once)
  })

  it('has nothing for no citations', () => {
    expect(numberBySection([])).toEqual([])
  })
})

describe('distinctSources', () => {
  it('has one entry per section, carrying the first citation of that section', () => {
    expect(distinctSources([ca1, ca2, co, citation({ marker: 2, sectionId: '4.3' })])).toEqual([
      ca1,
      co,
    ])
  })

  it('is one per section for the API per-passage numbers, with the first passage cited', () => {
    const sources = distinctSources(apiCitations())
    expect(sources.map((c) => [c.sectionId, c.passageId, c.marker])).toEqual([
      ['CA-4.3', 'CA-4.3~p1', 1],
      ['4.3', '4.3~p3', 2],
    ])
  })

  it('goes in the order the sections first appear', () => {
    expect(distinctSources([co, ca1]).map((c) => [c.sectionId, c.marker])).toEqual([
      ['4.3', 1],
      ['CA-4.3', 2],
    ])
  })

  it('lists the chips in text order for citations given out of order', () => {
    const sources = distinctSources([
      citation({ sectionId: '4.3', passageId: '4.3~p3', offsetUtf16: 50 }),
      citation({ sectionId: 'CA-4.3', offsetUtf16: 10 }),
    ])
    expect(sources.map((c) => [c.sectionId, c.marker])).toEqual([
      ['CA-4.3', 1],
      ['4.3', 2],
    ])
  })

  it('carries the passage cited first in the text, even when it is later in the array', () => {
    const sources = distinctSources([
      citation({ passageId: 'CA-4.3~p2', offsetUtf16: 60 }),
      citation({ passageId: 'CA-4.3~p1', offsetUtf16: 10 }),
    ])
    expect(sources.map((c) => c.passageId)).toEqual(['CA-4.3~p1'])
  })

  it('has nothing for no citations', () => {
    expect(distinctSources([])).toEqual([])
  })
})
