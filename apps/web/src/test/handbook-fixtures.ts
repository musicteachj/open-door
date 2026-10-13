import type { ParagraphPassage, PassageView, SectionSummary } from '@/api/generated'

/** A company section that applies to everyone (§4.3 Sick leave), with any field overridden. */
export function sectionSummary(overrides: Partial<SectionSummary> = {}): SectionSummary {
  return {
    id: '4.3',
    title: 'Sick leave',
    kind: 'company',
    chapter: 4,
    addendumState: null,
    groupName: 'Time off',
    audience: { states: [], employmentTypes: [], locations: [] },
    audienceLabel: 'Everyone',
    appliesToMe: true,
    lastUpdated: '2026-09-12',
    ...overrides,
  }
}

/** The California addendum to sick leave (CA-4.3), restricted to California employees. */
export function californiaSickLeave(overrides: Partial<SectionSummary> = {}): SectionSummary {
  return sectionSummary({
    id: 'CA-4.3',
    kind: 'addendum',
    chapter: null,
    addendumState: 'CA',
    groupName: 'California addendum',
    audience: { states: ['CA'], employmentTypes: [], locations: [] },
    audienceLabel: 'California employees',
    ...overrides,
  })
}

/** A paragraph passage, with its inline runs given as plain strings unless overridden. */
export function paragraph(id: string, text: string): ParagraphPassage {
  return {
    type: 'passage',
    id,
    kind: 'paragraph',
    inlines: [{ text, bold: false, italic: false, linkSectionId: null }],
  }
}

/** What the passage route returns for CA-4.3's second paragraph, with a neighbor on each side. */
export function passageView(overrides: Partial<PassageView> = {}): PassageView {
  return {
    section: californiaSickLeave(),
    previous: paragraph('p1', 'California employees receive 40 hours of paid sick leave.'),
    passage: paragraph('p2', 'You can use sick leave for your own illness or to care for family.'),
    next: paragraph('p3', 'Tell your manager as soon as you can.'),
    ...overrides,
  }
}
