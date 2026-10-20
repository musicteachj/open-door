import type { CitationOut, ToolCallOut } from '@/api/generated'

/** A citation of the California sick leave addendum, marker 1, with any field overridden. */
export function citation(overrides: Partial<CitationOut> = {}): CitationOut {
  return {
    marker: 1,
    offsetUtf16: 0,
    sectionId: 'CA-4.3',
    passageId: 'CA-4.3~p1',
    title: 'Sick leave',
    groupName: 'California addendum',
    audienceLabel: 'California employees',
    lastUpdated: '2026-09-12',
    deepLink: '/handbook/CA-4.3?passage=CA-4.3~p1',
    citedText: 'Employees accrue paid sick leave.',
    ...overrides,
  }
}

/**
 * Citations as the API sends them: it numbers each distinct passage, so two passages of one
 * section get markers 1 and 2, and the next section's passage is 3. A passage cited twice repeats
 * its number. The design numbers by section, which `numberBySection` does.
 */
export function apiCitations(): CitationOut[] {
  return [
    citation({ marker: 1, passageId: 'CA-4.3~p1', offsetUtf16: 10 }),
    citation({ marker: 1, passageId: 'CA-4.3~p1', offsetUtf16: 30 }),
    citation({ marker: 2, passageId: 'CA-4.3~p2', offsetUtf16: 50 }),
    citation({
      marker: 3,
      sectionId: '4.3',
      passageId: '4.3~p3',
      groupName: 'Company handbook',
      offsetUtf16: 70,
    }),
  ]
}

/** A "Show your work" tool call, with any field overridden. */
export function toolCall(overrides: Partial<ToolCallOut> = {}): ToolCallOut {
  return {
    name: 'search_handbook',
    inputSummary: "query='sick leave', location=CA",
    ok: true,
    durationMs: 120,
    ...overrides,
  }
}

/** The two sections the design's sick leave answer cites, plus two it retrieved and did not cite. */
export const SICK_LEAVE_SECTIONS = [
  {
    sectionId: 'CA-4.3',
    passageIds: ['CA-4.3~p1', 'CA-4.3~p2'],
    title: 'Sick leave',
    groupName: 'California addendum',
  },
  { sectionId: '4.3', passageIds: ['4.3~p3'], title: 'Sick leave', groupName: 'Company handbook' },
  {
    sectionId: 'CO-4.3',
    passageIds: ['CO-4.3~p1'],
    title: 'Sick leave',
    groupName: 'Colorado addendum',
  },
  {
    sectionId: '4.1',
    passageIds: ['4.1~p1'],
    title: 'Paid time off',
    groupName: 'Company handbook',
  },
]

/** Dana Whitfield, as the directory sends her once the API adds a title and a location. */
export const DANA = {
  name: 'Dana Whitfield',
  workEmail: 'dana.whitfield@juniperrow.example',
  jobTitle: 'HR Business Partner',
  locationName: 'Denver HQ',
}
