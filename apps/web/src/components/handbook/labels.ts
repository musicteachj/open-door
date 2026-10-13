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
  closePassage: 'Close passage',
  openInHandbook: 'Open in handbook',
  passageError: "Couldn't load this passage.",
  missingTitle: "This section isn't in your handbook version.",
  backToHandbook: 'Back to the handbook',
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

/** An addendum group's note, "For California employees". An unknown state shows its code. */
export function addendumGroupNote(addendumState: string): string {
  return `For ${STATE_NAMES[addendumState] ?? addendumState} employees`
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
