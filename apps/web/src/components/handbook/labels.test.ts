import { describe, expect, it } from 'vitest'
import { californiaSickLeave, sectionSummary } from '@/test/handbook-fixtures'
import {
  addendumGroupNote,
  notApplicableNote,
  stateRulesNote,
  sectionNumber,
  stateName,
  handbookPath,
  appliesToLabel,
  chapterNavHeading,
  handbookCopy,
  lastUpdatedText,
  markerShownInList,
  panelEyebrow,
  searchResultSource,
  sectionEyebrow,
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
    expect(addendumGroupNote('GA')).toBe('For Georgia employees')
    expect(addendumGroupNote('TX')).toBe('For Texas employees')
  })

  it('falls back to the code itself for a state it does not know', () => {
    expect(addendumGroupNote('NY')).toBe('For NY employees')
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

describe('the section page copy', () => {
  it('writes a section number with a section sign only for a company section', () => {
    expect(sectionNumber('4.3')).toBe('§4.3')
    expect(sectionNumber('CA-4.3')).toBe('CA-4.3')
  })

  it('names a state from its code, or shows the code', () => {
    expect(stateName('TX')).toBe('Texas')
    expect(stateName('GA')).toBe('Georgia')
    expect(stateName('NY')).toBe('NY')
  })

  it('writes the note for a section that does not apply, keeping a state name capitalized', () => {
    expect(handbookCopy.notApplicable('California employees', 'Austin warehouse', 'TX')).toBe(
      'This section is for California employees. You work at the Austin warehouse in Texas.',
    )
    expect(handbookCopy.notApplicable('Hourly staff in California', 'Denver HQ', 'CO')).toBe(
      'This section is for hourly staff in California. You work at the Denver HQ in Colorado.',
    )
  })

  it('writes the link to the company section', () => {
    expect(handbookCopy.seeWhatApplies('4.3', 'Sick leave')).toBe(
      'See what applies to you: §4.3 Sick leave',
    )
  })

  it('says what is missing, with the version when it is known', () => {
    expect(handbookCopy.missingBody('8.2', '2026.10')).toBe(
      "There's no §8.2 in version 2026.10 of the Juniper Row handbook.",
    )
    expect(handbookCopy.missingBody('ZZ-1.1', null)).toBe(
      "There's no ZZ-1.1 in the Juniper Row handbook.",
    )
  })
})

describe('stateRulesNote', () => {
  it('names one, two, or three states', () => {
    expect(stateRulesNote(['CA'])).toBe('California adds to this section.')
    expect(stateRulesNote(['CA', 'CO'])).toBe('California and Colorado add to this section.')
    expect(stateRulesNote(['CA', 'CO', 'TX'])).toBe(
      'California, Colorado, and Texas add to this section.',
    )
  })
})

describe('audienceForSentence, through the notes', () => {
  const austin = { id: 'u-3', code: 'aus', name: 'Austin warehouse', state: 'TX' }
  const note = (audienceLabel: string) =>
    notApplicableNote(
      { audience: { states: ['CA'], employmentTypes: [], locations: [] }, audienceLabel },
      { location: austin, employmentType: 'hourly' },
    )

  it('keeps a state name, a location name, and lowercases an employment type', () => {
    expect(note('California employees')).toMatch(/^This section is for California employees\./)
    expect(note('Denver HQ')).toMatch(/^This section is for Denver HQ\./)
    expect(note('Hourly staff in California')).toMatch(
      /^This section is for hourly staff in California\./,
    )
    expect(note('Salaried staff')).toMatch(/^This section is for salaried staff\./)
  })
})

describe('notApplicableNote', () => {
  const oakland = { id: 'u-1', code: 'oak', name: 'Oakland store', state: 'CA' }
  const austin = { id: 'u-3', code: 'aus', name: 'Austin warehouse', state: 'TX' }
  const denver = { id: 'u-2', code: 'den', name: 'Denver HQ', state: 'CO' }
  const caAudience = { states: ['CA'], employmentTypes: [], locations: [] }
  const caHourly = { states: ['CA'], employmentTypes: ['hourly'], locations: [] }
  const denverHourly = { states: [], employmentTypes: ['hourly'], locations: ['den'] }

  it('names where the person works when the state is why the section is not theirs', () => {
    expect(
      notApplicableNote(
        { audience: caAudience, audienceLabel: 'California employees' },
        { location: austin, employmentType: 'hourly' },
      ),
    ).toBe('This section is for California employees. You work at the Austin warehouse in Texas.')
  })

  it('says so when the employment type is why, in the right state', () => {
    expect(
      notApplicableNote(
        { audience: caHourly, audienceLabel: 'Hourly staff in California' },
        { location: oakland, employmentType: 'salaried' },
      ),
    ).toBe(
      "This section is for hourly staff in California. You're salaried, at the Oakland store in California.",
    )
  })

  it('names the state first when both the state and the type differ', () => {
    expect(
      notApplicableNote(
        { audience: caHourly, audienceLabel: 'Hourly staff in California' },
        { location: austin, employmentType: 'salaried' },
      ),
    ).toBe(
      'This section is for hourly staff in California. You work at the Austin warehouse in Texas.',
    )
  })

  it("says the employment type is why when the person is at the section's location", () => {
    expect(
      notApplicableNote(
        { audience: denverHourly, audienceLabel: 'Hourly staff at Denver HQ' },
        { location: denver, employmentType: 'salaried' },
      ),
    ).toBe(
      "This section is for hourly staff at Denver HQ. You're salaried, at the Denver HQ in Colorado.",
    )
  })

  it('names the place when the person is at a different location', () => {
    expect(
      notApplicableNote(
        { audience: denverHourly, audienceLabel: 'Hourly staff at Denver HQ' },
        { location: austin, employmentType: 'salaried' },
      ),
    ).toBe(
      'This section is for hourly staff at Denver HQ. You work at the Austin warehouse in Texas.',
    )
  })
})
