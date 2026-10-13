import { describe, expect, it } from 'vitest'
import { californiaSickLeave, sectionSummary } from '@/test/handbook-fixtures'
import {
  addendumGroupNote,
  handbookPath,
  appliesToLabel,
  chapterNavHeading,
  handbookCopy,
  lastUpdatedText,
  markerShownInList,
  panelEyebrow,
  searchResultSource,
  sectionEyebrow,
  sectionRowLabel,
} from './labels'

describe('handbookCopy', () => {
  it('holds the fixed strings from the screen notes', () => {
    expect(handbookCopy).toMatchObject({
      title: 'Employee handbook',
      searchLabel: 'Search the handbook',
      clearSearch: 'Clear search',
      columns: { section: 'Section', appliesTo: 'Applies to', lastUpdated: 'Last updated' },
      addendaHeading: 'State addenda',
      addendaNote: 'Each addendum section supplements the company section with the same number.',
      marker: { yes: 'Applies to you', no: "Doesn't apply to you" },
      back: '← Handbook',
      closePassage: 'Close passage',
      openInHandbook: 'Open in handbook',
      passageError: "Couldn't load this passage.",
    })
  })
})

describe('lastUpdatedText', () => {
  it('writes the date out', () => {
    expect(lastUpdatedText('2026-09-12')).toBe('Last updated Sep 12, 2026')
  })
})

describe('appliesToLabel', () => {
  it('prefixes the API label', () => {
    expect(appliesToLabel('California employees')).toBe('Applies to: California employees')
  })
})

describe('sectionEyebrow', () => {
  it('writes a company section with a section sign', () => {
    expect(sectionEyebrow(sectionSummary())).toBe('§4.3 · Time off')
  })

  it('writes an addendum with its code and no section sign', () => {
    expect(sectionEyebrow(californiaSickLeave())).toBe('CA-4.3 · California addendum')
  })
})

describe('panelEyebrow', () => {
  it('puts "Handbook" in front of the section eyebrow', () => {
    expect(panelEyebrow(sectionSummary())).toBe('Handbook §4.3 · Time off')
    expect(panelEyebrow(californiaSickLeave())).toBe('Handbook CA-4.3 · California addendum')
  })
})

describe('chapterNavHeading', () => {
  it('is "Chapter 4 · Time off" for a chapter and the addendum name for an addendum', () => {
    expect(chapterNavHeading(sectionSummary())).toBe('Chapter 4 · Time off')
    expect(chapterNavHeading(californiaSickLeave())).toBe('California addendum')
  })
})

describe('addendumGroupNote', () => {
  it('says who the addendum is for', () => {
    expect(addendumGroupNote('CA')).toBe('For California employees')
    expect(addendumGroupNote('CO')).toBe('For Colorado employees')
    expect(addendumGroupNote('TX')).toBe('For Texas employees')
  })

  it('falls back to the code itself for a state it does not know', () => {
    expect(addendumGroupNote('GA')).toBe('For GA employees')
  })
})

describe('searchResultSource', () => {
  it('is "Company handbook" or the addendum name', () => {
    expect(searchResultSource(sectionSummary())).toBe('Company handbook')
    expect(searchResultSource(californiaSickLeave())).toBe('California addendum')
  })
})

describe('markerShownInList', () => {
  it('shows only when the section applies to me and has a restricted audience', () => {
    expect(markerShownInList(californiaSickLeave())).toBe(true)
  })

  it('never shows on an everyone row, whatever its label says', () => {
    expect(markerShownInList(sectionSummary())).toBe(false)
    expect(markerShownInList(sectionSummary({ audienceLabel: 'California employees' }))).toBe(false)
  })

  it('does not show on a restricted section that does not cover me', () => {
    expect(markerShownInList(californiaSickLeave({ appliesToMe: false }))).toBe(false)
  })

  it('counts an employment type or a location as restricted', () => {
    const hourly = sectionSummary({
      audience: { states: [], employmentTypes: ['hourly'], locations: [] },
    })
    const denver = sectionSummary({
      audience: { states: [], employmentTypes: [], locations: ['denver-hq'] },
    })
    expect(markerShownInList(hourly)).toBe(true)
    expect(markerShownInList(denver)).toBe(true)
  })
})

describe('sectionRowLabel', () => {
  it('is the number, title, audience, and date', () => {
    expect(sectionRowLabel(sectionSummary(), false)).toBe(
      '4.3 Sick leave. Applies to Everyone. Last updated Sep 12, 2026',
    )
  })

  it('adds the marker when it is shown', () => {
    expect(sectionRowLabel(californiaSickLeave(), true)).toBe(
      'CA-4.3 Sick leave. Applies to California employees. Applies to you. Last updated Sep 12, 2026',
    )
  })
})

describe('handbookPath', () => {
  it('is the section page', () => {
    expect(handbookPath('4.3')).toBe('/handbook/4.3')
    expect(handbookPath('CA-4.3')).toBe('/handbook/CA-4.3')
  })

  it('adds the passage to highlight', () => {
    expect(handbookPath('CA-4.3', 'p2')).toBe('/handbook/CA-4.3?passage=p2')
  })

  it('encodes both parts, so a passage ID cannot add a parameter', () => {
    expect(handbookPath('a/b c', 'p 2&x=1')).toBe('/handbook/a%2Fb%20c?passage=p%202%26x%3D1')
  })
})
