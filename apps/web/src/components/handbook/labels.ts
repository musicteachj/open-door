// The handbook's words and accessible names, in one tested place (the Copy section of
// docs/design/screens/06-handbook/notes.md). A component calls these instead of building its own
// string. Dates come from the API as ISO calendar dates and are written out here.
import type { SectionSummary } from '@/api/generated'
import { formatShortDate } from '@/lib/time'

export const handbookCopy = {
  title: 'Employee handbook',
  demoNotice:
    'Juniper Row is a fictional company. This handbook is demo content, not legal advice.',
  searchLabel: 'Search the handbook',
  clearSearch: 'Clear search',
  askAssistant: 'Ask the assistant',
  showAllSections: 'Show all sections',
  noneApplyMatch: (query: string) => `No sections that apply to you match “${query}.”`,
  noMatch: (query: string) => `No sections match “${query}.”`,
  filterAll: 'All sections',
  filterApplies: 'Applies to me',
  columns: { section: 'Section', appliesTo: 'Applies to', lastUpdated: 'Last updated' },
  addendaHeading: 'State addenda',
  addendaNote: 'Each addendum section supplements the company section with the same number.',
  appliesPrefix: 'Applies to:',
  marker: { yes: 'Applies to you', no: "Doesn't apply to you" },
  back: '← Handbook',
  citedPassage: 'Cited passage',
  clearHighlight: 'Clear highlight',
  sourcesHeading: 'Sources',
  previous: 'Previous',
  next: 'Next',
  stateRules: 'State rules',
  supplements: 'Supplements',
  companyHandbook: 'Company handbook',
  previousAndNext: 'Previous and next',
  closePassage: 'Close passage',
  openInHandbook: 'Open in handbook',
  passageError: "Couldn't load this passage.",
  missingTitle: "This section isn't in your handbook version.",
  backToHandbook: 'Back to the handbook',
  missingBody: (id: string, versionLabel: string | null) =>
    `There's no ${sectionNumber(id)} in ${versionLabel ? `version ${versionLabel} of the Juniper Row handbook` : 'the Juniper Row handbook'}.`,
  /** "This section is for California employees. You work at the Austin warehouse in Texas." */
  notApplicable: (audienceLabel: string, locationName: string, stateCode: string) =>
    `This section is for ${audienceForSentence(audienceLabel)}. You work at the ${locationName} in ${stateName(stateCode)}.`,
  /** "This section is for hourly staff in California. You're salaried, at the Oakland store in California." */
  notApplicableEmployment: (
    audienceLabel: string,
    employmentType: string,
    locationName: string,
    stateCode: string,
  ) =>
    `This section is for ${audienceForSentence(audienceLabel)}. You're ${employmentType}, at the ${locationName} in ${stateName(stateCode)}.`,
  seeWhatApplies: (id: string, title: string) =>
    `See what applies to you: ${sectionNumber(id)} ${title}`,
  loading: {
    handbook: 'Loading the handbook',
    section: 'Loading section',
    passage: 'Loading passage',
  },
} as const

/** "Last updated Sep 12, 2026". */
export function lastUpdatedText(isoDate: string): string {
  return `Last updated ${formatShortDate(isoDate)}`
}

/** "Applies to: California employees". */
export function appliesToLabel(audienceLabel: string): string {
  return `${handbookCopy.appliesPrefix} ${audienceLabel}`
}

/** "§4.3 · Time off" for a company section, "CA-4.3 · California addendum" for an addendum. */
export function sectionEyebrow(section: Pick<SectionSummary, 'id' | 'kind' | 'groupName'>): string {
  const number = section.kind === 'company' ? `§${section.id}` : section.id
  return `${number} · ${section.groupName}`
}

/** The passage panel's eyebrow: "Handbook §4.3 · Time off". */
export function panelEyebrow(section: Pick<SectionSummary, 'id' | 'kind' | 'groupName'>): string {
  return `Handbook ${sectionEyebrow(section)}`
}

/** The chapter navigator's heading: "Chapter 4 · Time off", or "California addendum". */
export function chapterNavHeading(
  section: Pick<SectionSummary, 'kind' | 'chapter' | 'groupName'>,
): string {
  return section.kind === 'company' && section.chapter !== null
    ? `Chapter ${section.chapter} · ${section.groupName}`
    : section.groupName
}

/** State codes to names. A new state's addendum is one line here. */
const STATE_NAMES: Record<string, string> = {
  CA: 'California',
  CO: 'Colorado',
  TX: 'Texas',
}

/** A state's name from its code ("TX" is "Texas"). An unknown state shows its code. */
export function stateName(code: string): string {
  return STATE_NAMES[code] ?? code
}

/**
 * An audience label inside a sentence. An employment-type label loses its capital ("Hourly staff"
 * is "hourly staff"); a state or a location is a name and keeps it ("California employees",
 * "Denver HQ").
 */
function audienceForSentence(label: string): string {
  return /^(hourly|salaried)\b/i.test(label)
    ? label.charAt(0).toLowerCase() + label.slice(1)
    : label
}

/** A section's number as the handbook writes it: "§4.3" for a company section, "CA-4.3" as is. */
export function sectionNumber(id: string): string {
  return /^\d/.test(id) ? `§${id}` : id
}

/** An addendum group's note, "For California employees". An unknown state shows its code. */
export function addendumGroupNote(addendumState: string): string {
  return `For ${stateName(addendumState)} employees`
}

/** A section's page, optionally with the passage to highlight. Both parts are encoded. */
export function handbookPath(sectionId: string, passageId?: string): string {
  const path = `/handbook/${encodeURIComponent(sectionId)}`
  return passageId === undefined ? path : `${path}?passage=${encodeURIComponent(passageId)}`
}

/** Where a search result comes from: "Company handbook" or "California addendum". */
export function searchResultSource(section: Pick<SectionSummary, 'kind' | 'groupName'>): string {
  return section.kind === 'company' ? handbookCopy.companyHandbook : section.groupName
}

/**
 * In the section list the marker shows only when the section covers the person and its audience
 * is restricted. The audience lists decide, not the label's text: an empty audience is everyone.
 */
export function markerShownInList(
  section: Pick<SectionSummary, 'appliesToMe' | 'audience'>,
): boolean {
  const { states, employmentTypes, locations } = section.audience
  const restricted = states.length + employmentTypes.length + locations.length > 0
  return section.appliesToMe && restricted
}

/** A section row, which is one link: number, title, audience, the marker if shown, the date. */
export function sectionRowLabel(
  section: Pick<SectionSummary, 'id' | 'title' | 'audienceLabel' | 'lastUpdated'>,
  markerShown: boolean,
): string {
  const marker = markerShown ? `. ${handbookCopy.marker.yes}` : ''
  return `${section.id} ${section.title}. Applies to ${section.audienceLabel}${marker}. ${lastUpdatedText(section.lastUpdated)}`
}

/** "California and Colorado add to this section.", from the addenda's state codes. */
export function stateRulesNote(stateCodes: string[]): string {
  const names = stateCodes.map(stateName)
  const list =
    names.length > 2 ? `${names.slice(0, -1).join(', ')}, and ${names.at(-1)}` : names.join(' and ')
  return `${list} ${names.length === 1 ? 'adds' : 'add'} to this section.`
}

/**
 * The neutral note for a section that isn't for the reader. The state or the location decides
 * first: where they work is the plainest reason. Only when they are in the right place does it
 * say their employment type is why.
 */
export function notApplicableNote(
  section: { audience: SectionSummary['audience']; audienceLabel: string },
  me: {
    location: { code: string; name: string; state: string }
    employmentType: string
  },
): string {
  const { states, employmentTypes, locations } = section.audience
  const placeDiffers =
    (states.length > 0 && !states.includes(me.location.state)) ||
    (locations.length > 0 && !locations.includes(me.location.code))
  if (!placeDiffers && employmentTypes.length > 0 && !employmentTypes.includes(me.employmentType)) {
    return handbookCopy.notApplicableEmployment(
      section.audienceLabel,
      me.employmentType,
      me.location.name,
      me.location.state,
    )
  }
  return handbookCopy.notApplicable(section.audienceLabel, me.location.name, me.location.state)
}
