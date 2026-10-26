import { useRef, useState } from 'react'
import type {
  Inline,
  ListPassage,
  ParagraphPassage,
  PassageView,
  SearchResultOut,
  SectionDetail,
  SectionRef,
  SectionSummary,
} from '@/api/generated'
import { ApplicabilityBadge } from '@/components/handbook/applicability-badge'
import { AppliesMarker } from '@/components/handbook/applies-marker'
import { ChapterNav } from '@/components/handbook/chapter-nav'
import { CitedPassage } from '@/components/handbook/cited-passage'
import { HandbookBlocks, PassageText } from '@/components/handbook/handbook-blocks'
import { LastUpdated } from '@/components/handbook/last-updated'
import { LinkBlock } from '@/components/handbook/link-block'
import { PassagePanel } from '@/components/handbook/passage-panel'
import { SearchResultRow } from '@/components/handbook/search-result-row'
import { SectionGroup } from '@/components/handbook/section-group'
import { SectionRow } from '@/components/handbook/section-row'
import { SourcesBlock } from '@/components/handbook/sources-block'
import { Textarea } from '@/components/ui/textarea'
import { Group, Section } from '../gallery-parts'

// The handbook components, from Juniper Row's real section IDs and titles. Hover and focus are not
// shown: the tests hover and focus the real elements. Links lead to handbook routes that the
// gallery has no page for. The two passage panels that show a passage start closed, behind a
// button, because an open panel moves focus to its title and that must not happen on page load.

const EVERYONE = { states: [], employmentTypes: [], locations: [] }
const DATE = '2026-10-07'

function summary(overrides: Partial<SectionSummary>): SectionSummary {
  return {
    id: '4.3',
    title: 'Sick leave',
    kind: 'company',
    chapter: 4,
    addendumState: null,
    groupName: 'Time off',
    audience: EVERYONE,
    audienceLabel: 'Everyone',
    appliesToMe: true,
    lastUpdated: DATE,
    ...overrides,
  }
}

const addendum = (
  state: 'CA' | 'CO' | 'TX',
  id: string,
  title: string,
  appliesToMe: boolean,
  employmentTypes: string[] = [],
): SectionSummary => {
  const name = { CA: 'California', CO: 'Colorado', TX: 'Texas' }[state]
  return summary({
    id,
    title,
    kind: 'addendum',
    chapter: null,
    addendumState: state,
    groupName: `${name} addendum`,
    audience: { ...EVERYONE, states: [state], employmentTypes },
    audienceLabel: employmentTypes.length > 0 ? `Hourly staff in ${name}` : `${name} employees`,
    appliesToMe,
  })
}

const SICK = summary({})
const OVERTIME = summary({
  id: '3.2',
  title: 'Overtime',
  chapter: 3,
  groupName: 'Hours and pay',
  audience: { ...EVERYONE, employmentTypes: ['hourly'] },
  audienceLabel: 'Hourly staff',
  appliesToMe: false,
})
const PTO = summary({ id: '4.1', title: 'Paid time off' })
const HOLIDAYS = summary({ id: '4.2', title: 'Holidays' })
const BEREAVEMENT = summary({ id: '4.4', title: 'Bereavement leave' })
const JURY = summary({ id: '4.5', title: 'Jury duty and voting' })
const CA_SICK = addendum('CA', 'CA-4.3', 'Sick leave', true)
const CO_SICK = addendum('CO', 'CO-4.3', 'Sick leave', false)
// CA-3.2 and CA-3.3 apply to hourly staff in California, as their front matter says.
const CA_OVERTIME = addendum('CA', 'CA-3.2', 'Overtime', true, ['hourly'])
const HOURLY_CA = addendum('CA', 'CA-3.3', 'Meal and rest breaks', true, ['hourly'])
const CHAPTER_FOUR = [PTO, HOLIDAYS, SICK, BEREAVEMENT, JURY]
const CA_SECTIONS = [
  CA_OVERTIME,
  HOURLY_CA,
  addendum('CA', 'CA-3.4', 'Paydays and final pay', true),
  CA_SICK,
  addendum('CA', 'CA-5.1', 'Family and medical leave', true),
]

const run = (text: string, extra: Partial<Inline> = {}): Inline => ({
  text,
  bold: false,
  italic: false,
  linkSectionId: null,
  ...extra,
})
const para = (id: string, ...inlines: Inline[]): ParagraphPassage => ({
  type: 'passage',
  id,
  kind: 'paragraph',
  inlines,
})
const list = (id: string, ordered: boolean, ...items: string[]): ListPassage => ({
  type: 'passage',
  id,
  kind: 'list',
  ordered,
  items: items.map((item) => [run(item)]),
})

// Text is verbatim from the handbook. The headings and the first paragraph and list are CA-4.3's
// (handbook/addenda/ca/CA-4.3-sick-leave.md). The numbered list is §2.3 "Ways to raise a concern".
// No real section has italic text, so "up-front method" (CA-4.3's own words) is italicized here,
// and "40 hours" is bolded, only to show those styles. The link is CA-4.3's own link to §4.3.
const BLOCKS: SectionDetail['blocks'] = [
  { type: 'heading', level: 2, text: 'How much you receive' },
  para(
    'p1',
    run('In California you receive at least '),
    run('40 hours', { bold: true }),
    run(
      ', or 5 of your workdays, of paid sick leave each year, whichever is more. You receive all of it on January 1. This is called the ',
    ),
    run('up-front method', { italic: true }),
    run('. It adds to '),
    run('§4.3 Sick leave', { linkSectionId: '4.3' }),
    run('.'),
  ),
  { type: 'heading', level: 3, text: 'What you can use it for' },
  para('p2', run('You can use sick leave for:')),
  list(
    'p3',
    false,
    'diagnosis, care, or treatment of an existing health condition, for you or a family member',
    'preventive care, for you or a family member',
    'serving on a jury, or appearing in court as a witness under a subpoena or court order',
    'reasons related to being a victim of a qualifying act of violence, such as domestic violence, sexual assault, or stalking, for you or a family member',
  ),
  { type: 'heading', level: 2, text: 'Ways to raise a concern' },
  list(
    'p4',
    true,
    'Write to HR in Open Door. Your message opens a confidential case that only the HR team sees.',
    'Send an email to the HR team.',
    'Ask for a private meeting with someone in HR, in person or by phone.',
  ),
]

const SOURCES = [
  'California Labor Code §§245–249 (Healthy Workplaces, Healthy Families Act, as amended by SB 616): amount, up-front method, uses, and notice, read from https://www.dir.ca.gov/dlse/Paid_Sick_Leave.htm on 2026-10-07.',
  'California Labor Code §246: no accrual or carryover required under the up-front method, and jury and court uses, read from the DLSE Paid Sick Leave Posting (amended effective 1/1/2026) at https://www.dir.ca.gov/DLSE/Publications/Paid_Sick_Days_Poster_Template_(11_2014).pdf on 2026-10-07.',
]

const refs = (sections: SectionSummary[]): SectionRef[] =>
  sections.map(({ id, title, groupName, audienceLabel, appliesToMe }) => ({
    id,
    title,
    groupName,
    audienceLabel,
    appliesToMe,
  }))

const results = (...parts: [SectionSummary, string, [string, boolean][]][]): SearchResultOut[] =>
  parts.map(([section, passageId, excerpt]) => ({
    section,
    passageId,
    excerpt: excerpt.map(([text, match]) => ({ text, match })),
  }))

const SEARCH_RESULTS = results(
  [
    CA_OVERTIME,
    'p1',
    [
      ['California counts ', false],
      ['overtime', true],
      [' by the day as well as by the week.', false],
    ],
  ],
  [
    OVERTIME,
    'p2',
    [
      ['Under federal law, non-exempt employees must be paid ', false],
      ['overtime', true],
      [' at time and one-half their regular rate for hours worked over 40 in a workweek.', false],
    ],
  ],
)

// Verbatim sentences from CA-4.3 ("Notes and notice", "What happens to unused hours", "Longer
// illness"), run together into one long paragraph so the panel's body has to scroll.
const LONG_PASSAGE = para(
  'p5',
  run(
    "Juniper Row does not ask for a doctor's note to use sick leave in California, so the note rule in the company section does not apply to you. When you know about the need ahead of time, give your manager advance notice. When you do not, tell your manager as soon as practical. Because you receive the full amount at the start of each year, unused hours do not carry over. The new amount replaces them. Unused sick leave is not paid out when your employment ends. If you are rehired within 12 months, your unused sick leave is restored. If you need more time than your sick leave covers, see ",
  ),
  run('§CA-5.1 California family and medical leave', { linkSectionId: 'CA-5.1' }),
  run('.'),
)

const VIEW: PassageView = {
  section: CA_SICK,
  previous: para(
    'p1',
    run(
      'In California you receive at least 40 hours, or 5 of your workdays, of paid sick leave each year, whichever is more. You receive all of it on January 1. This is called the up-front method.',
    ),
  ),
  passage: para(
    'p2',
    run(
      'A new hire receives the full amount on their first day and can use it right away. Juniper Row does not make you wait before you use it.',
    ),
  ),
  next: para('p3', run('You can use sick leave for:')),
}

const LONG_VIEW: PassageView = {
  section: { ...CA_SICK, appliesToMe: false },
  previous: VIEW.previous,
  passage: LONG_PASSAGE,
  next: VIEW.next,
}

const noop = () => {}

/** Opens a panel from a button and, on close, puts focus back on that button, as a real host puts
 * it back on the citation. The textarea is a field outside the panel, for the Escape test. */
function PanelHost({ view, openLabel }: { view: PassageView; openLabel: string }) {
  const [open, setOpen] = useState(false)
  const openRef = useRef<HTMLButtonElement>(null)
  const close = () => {
    setOpen(false)
    // Focus returns after the panel unmounts.
    queueMicrotask(() => openRef.current?.focus())
  }
  return (
    <div className="flex w-full flex-wrap items-start gap-6">
      <div className="flex w-72 flex-col gap-3">
        <button
          ref={openRef}
          type="button"
          onClick={() => setOpen(true)}
          className="h-9 w-fit cursor-pointer rounded-md border border-border-strong px-3 text-ui"
        >
          {openLabel}
        </button>
        <Textarea aria-label="A message outside the panel" placeholder="Type, then press Escape" />
      </div>
      {open && (
        <div className="h-[640px] w-panel max-w-full overflow-hidden rounded-lg border border-border">
          <PassagePanel
            state="open"
            sectionId={view.section.id}
            passageId={view.passage.id}
            view={view}
            onClose={close}
          />
        </div>
      )}
    </div>
  )
}

function PanelFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-[640px] w-panel max-w-full overflow-hidden rounded-lg border border-border">
      {children}
    </div>
  )
}

export function HandbookSections() {
  return (
    <>
      <Group title="Handbook: badge, marker, and last updated">
        <Section
          id="applicability-badge-chip"
          title="Applicability badge, chip (Hourly staff in California)"
        >
          <ApplicabilityBadge label="Everyone" />
          <ApplicabilityBadge label="California employees" />
          <ApplicabilityBadge label="Hourly staff in California" />
        </Section>
        <Section id="applicability-badge-text" title="Applicability badge, text (the list column)">
          <ApplicabilityBadge variant="text" label="California employees" />
        </Section>
        <Section id="applies-marker-applies" title="Applies marker, applies">
          <AppliesMarker applies />
        </Section>
        <Section id="applies-marker-not" title="Applies marker, doesn't apply">
          <AppliesMarker applies={false} />
        </Section>
        <Section id="last-updated-default" title="Last updated">
          <LastUpdated date={DATE} />
        </Section>
      </Group>

      {/* The list rows and groups break out of the gallery's 760 px column to a realistic list
          width, so the six-column row shows as designed. The row itself switches to its stacked
          layout by its own width (a container query), as on the narrow state below. */}
      <div className="relative left-1/2 w-[min(68rem,calc(100vw_-_4rem))] shrink-0 -translate-x-1/2">
        <Group title="Handbook: section rows, groups, and chapter navigator">
          <Section
            id="section-row-default"
            title="Section row, default (applies to everyone, no marker)"
          >
            <ul className="m-0 w-full list-none p-0">
              <SectionRow section={PTO} />
            </ul>
          </Section>
          <Section id="section-row-current" title="Section row, current">
            <ul className="m-0 w-full list-none p-0">
              <SectionRow section={SICK} current />
            </ul>
          </Section>
          <Section
            id="section-row-marker"
            title="Section row, with the marker (restricted and covers you)"
          >
            <ul className="m-0 w-full list-none p-0">
              <SectionRow section={HOURLY_CA} />
            </ul>
          </Section>
          <Section
            id="section-row-no-marker"
            title="Section row, restricted but not yours (no marker)"
          >
            <ul className="m-0 w-full list-none p-0">
              <SectionRow section={OVERTIME} />
            </ul>
          </Section>
          <Section id="section-row-addendum" title="Section row, addendum">
            <ul className="m-0 w-full list-none p-0">
              <SectionRow section={CA_SICK} />
            </ul>
          </Section>
          <Section id="section-row-narrow" title="Section row, narrow (390 px, columns stacked)">
            <ul className="m-0 w-[390px] max-w-full list-none p-0">
              <SectionRow section={HOURLY_CA} />
            </ul>
          </Section>
          <Section id="section-group-chapter" title="Section group, a chapter">
            <div className="w-full">
              <SectionGroup id="gallery-chapter-4" num="4" title="Time off">
                {CHAPTER_FOUR.map((s) => (
                  <SectionRow key={s.id} section={s} />
                ))}
              </SectionGroup>
            </div>
          </Section>
          <Section id="section-group-addendum" title="Section group, a state addendum">
            <div className="w-full">
              <SectionGroup
                id="gallery-addendum-ca"
                num="CA"
                title="California addendum"
                note="For California employees"
              >
                {CA_SECTIONS.map((s) => (
                  <SectionRow key={s.id} section={s} />
                ))}
              </SectionGroup>
            </div>
          </Section>
          <Section
            id="chapter-nav-chapter"
            title="Chapter navigator, a chapter with its current section"
          >
            <div className="w-64">
              <ChapterNav section={SICK} sections={CHAPTER_FOUR} />
            </div>
          </Section>
          <Section id="chapter-nav-addendum" title="Chapter navigator, an addendum">
            <div className="w-64">
              <ChapterNav section={CA_SICK} sections={CA_SECTIONS} />
            </div>
          </Section>
        </Group>
      </div>

      <Group title="Handbook: search results">
        <Section id="search-result-applies" title="Search result row, applies to you">
          <ul className="m-0 w-full list-none p-0">
            <SearchResultRow result={SEARCH_RESULTS[0]!} />
          </ul>
        </Section>
        <Section id="search-result-not" title="Search result row, doesn't apply to you">
          <ul className="m-0 w-full list-none p-0">
            <SearchResultRow result={SEARCH_RESULTS[1]!} />
          </ul>
        </Section>
      </Group>

      <Group title="Handbook: section body and cited passage">
        <Section
          id="handbook-blocks-default"
          title="Handbook blocks, headings, paragraphs, both lists, bold, italic, and a link"
        >
          <div className="w-full max-w-[760px]">
            <HandbookBlocks blocks={BLOCKS} />
          </div>
        </Section>
        <Section
          id="handbook-blocks-cited"
          title="Handbook blocks, with a cited passage and Clear highlight"
        >
          <div className="w-full max-w-[760px]">
            <HandbookBlocks blocks={BLOCKS} citedPassageId="p1" onClearCitation={noop} />
          </div>
        </Section>
        <Section id="cited-passage-default" title="Cited passage, on the section page">
          <div className="w-full max-w-[760px] px-5">
            <CitedPassage onClear={noop}>
              <PassageText passage={VIEW.passage} />
            </CitedPassage>
          </div>
        </Section>
        <Section id="cited-passage-compact" title="Cited passage, compact (in the panel)">
          <div className="w-panel max-w-full px-3">
            <CitedPassage compact>
              <PassageText passage={VIEW.passage} />
            </CitedPassage>
          </div>
        </Section>
      </Group>

      <Group title="Handbook: link block and sources">
        <Section
          id="link-block-state-rules"
          title="Link block, State rules (one applies, one doesn't)"
        >
          <div className="w-full max-w-[760px]">
            <LinkBlock
              variant="stateRules"
              note="California and Colorado add to this section."
              sections={refs([CA_SICK, CO_SICK])}
            />
          </div>
        </Section>
        <Section id="link-block-supplements" title="Link block, Supplements">
          <div className="w-full max-w-[760px]">
            <LinkBlock variant="supplements" sections={refs([SICK])} />
          </div>
        </Section>
        <Section id="sources-block-default" title="Sources block">
          <div className="w-full max-w-[760px]">
            <SourcesBlock sources={SOURCES} />
          </div>
        </Section>
      </Group>

      <Group title="Handbook: passage panel">
        <Section id="passage-panel-open" title="Passage panel, open: press the button">
          <PanelHost view={VIEW} openLabel="Open the passage" />
        </Section>
        <Section
          id="passage-panel-long"
          title="Passage panel, a long passage that scrolls inside: press the button"
        >
          <PanelHost view={LONG_VIEW} openLabel="Open the long passage" />
        </Section>
        <Section id="passage-panel-loading" title="Passage panel, loading (with its group name)">
          <PanelFrame>
            <PassagePanel
              state="loading"
              sectionId="CA-4.3"
              passageId="p2"
              groupName="California addendum"
              onClose={noop}
            />
          </PanelFrame>
        </Section>
        <Section id="passage-panel-loading-bare" title="Passage panel, loading (no group name)">
          <PanelFrame>
            <PassagePanel state="loading" sectionId="CA-4.3" passageId="p2" onClose={noop} />
          </PanelFrame>
        </Section>
        <Section id="passage-panel-error" title="Passage panel, error with Retry">
          <PanelFrame>
            <PassagePanel
              state="error"
              sectionId="CA-4.3"
              passageId="p2"
              groupName="California addendum"
              onClose={noop}
              onRetry={noop}
            />
          </PanelFrame>
        </Section>
      </Group>
    </>
  )
}
