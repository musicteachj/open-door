import { http, HttpResponse } from 'msw'
import type {
  HandbookOverview,
  SearchResultOut,
  SectionDetail,
  SectionRef,
  SectionSummary,
} from '@/api/generated'
import { server } from './msw'

// A fake handbook API shaped like the real one, with the real section IDs and titles from
// handbook/. Each section's audience is the real one; `appliesToMe` is worked out here from the
// persona, as the server does from the person's state and employment type.
const url = (path: string) => `${window.location.origin}${path}`

type Who = { state: 'CA' | 'CO' | 'TX'; hourly: boolean }
/** Priya is a salaried employee in California; Mateo is an hourly employee in Texas. */
export const HANDBOOK_PERSONAS = {
  priya: { state: 'CA', hourly: false },
  mateo: { state: 'TX', hourly: true },
} as const satisfies Record<string, Who>

const CHAPTERS: Record<string, string> = {
  '1': 'Welcome',
  '2': 'Working here',
  '3': 'Hours and pay',
  '4': 'Time off',
  '5': 'Leaves of absence',
  '6': 'Health, safety, and support',
  '7': 'Privacy and confidential cases',
}
const ADDENDA: Record<string, string> = {
  CA: 'California addendum',
  CO: 'Colorado addendum',
  TX: 'Texas addendum',
}
const STATE_LABEL = { CA: 'California', CO: 'Colorado', TX: 'Texas' } as const

// id, title, state (for an addendum), hourly-only
type Row = [id: string, title: string, state?: 'CA' | 'CO' | 'TX', hourly?: boolean]
const ROWS: Row[] = [
  ['1.1', 'About this handbook'],
  ['1.2', 'Employment types'],
  ['2.1', 'Equal opportunity'],
  ['2.2', 'Harassment and discrimination'],
  ['2.3', 'Raising a concern'],
  ['2.4', 'Workplace conduct'],
  ['3.1', 'Schedules and timekeeping'],
  ['3.2', 'Overtime', undefined, true],
  ['3.3', 'Meal and rest breaks', undefined, true],
  ['3.4', 'Paydays and final pay'],
  ['4.1', 'Paid time off'],
  ['4.2', 'Holidays'],
  ['4.3', 'Sick leave'],
  ['4.4', 'Bereavement leave'],
  ['4.5', 'Jury duty and voting'],
  ['5.1', 'Family and medical leave'],
  ['5.2', 'Parental leave'],
  ['5.3', 'Accommodations'],
  ['6.1', 'Workplace safety'],
  ['6.2', 'Employee Assistance Program'],
  ['7.1', 'Your personal information'],
  ['7.2', 'How confidential HR cases work'],
  ['CA-3.2', 'Overtime', 'CA', true],
  ['CA-3.3', 'Meal and rest breaks', 'CA', true],
  ['CA-3.4', 'Paydays and final pay', 'CA'],
  ['CA-4.3', 'Sick leave', 'CA'],
  ['CA-5.1', 'Family and medical leave', 'CA'],
  ['CO-3.2', 'Overtime', 'CO', true],
  ['CO-3.3', 'Meal and rest breaks', 'CO', true],
  ['CO-3.4', 'Paydays and final pay', 'CO'],
  ['CO-4.3', 'Sick leave', 'CO'],
  ['CO-5.1', 'Family and medical leave', 'CO'],
  ['TX-3.4', 'Paydays and final pay', 'TX'],
  ['TX-4.5', 'Jury duty and voting', 'TX'],
]

function audienceLabel(state: Row[2], hourly: boolean): string {
  const type = hourly ? 'Hourly staff' : null
  if (state && type) return `${type} in ${STATE_LABEL[state]}`
  if (state) return `${STATE_LABEL[state]} employees`
  return type ?? 'Everyone'
}

/** Every section of the 2026.10 handbook as the API lists it, for one person. */
export function handbookSections(persona: keyof typeof HANDBOOK_PERSONAS): SectionSummary[] {
  const who: Who = HANDBOOK_PERSONAS[persona]
  return ROWS.map(([id, title, state, hourly = false]) => {
    const company = state === undefined
    return {
      id,
      title,
      kind: company ? 'company' : 'addendum',
      chapter: company ? Number(id.split('.')[0]) : null,
      addendumState: state ?? null,
      groupName: company ? CHAPTERS[id.split('.')[0]!]! : ADDENDA[state]!,
      audience: {
        states: state ? [state] : [],
        employmentTypes: hourly ? ['hourly'] : [],
        locations: [],
      },
      audienceLabel: audienceLabel(state, hourly),
      appliesToMe: (state === undefined || state === who.state) && (!hourly || who.hourly),
      lastUpdated: '2026-09-12',
    } as SectionSummary
  })
}

export function handbookOverview(persona: keyof typeof HANDBOOK_PERSONAS): HandbookOverview {
  return {
    version: { label: '2026.10', title: 'Juniper Row Employee Handbook', updatedOn: '2026-09-12' },
    chapters: CHAPTERS,
    addenda: ADDENDA,
    sections: handbookSections(persona),
  }
}

const ref = (s: SectionSummary): SectionRef => ({
  id: s.id,
  title: s.title,
  groupName: s.groupName,
  audienceLabel: s.audienceLabel,
  appliesToMe: s.appliesToMe,
})

const SOURCES: Record<string, string> = {
  CA: 'California Labor Code §246, read from dir.ca.gov on Oct 6, 2026.',
  CO: 'Colorado Revised Statutes §8-13.3-403, read from cdle.colorado.gov on Oct 6, 2026.',
  TX: 'Texas Labor Code §61.014, read from twc.texas.gov on Oct 6, 2026.',
}

const plain = (text: string) => [{ text, bold: false, italic: false, linkSectionId: null }]
const para = (id: string, text: string) =>
  ({ type: 'passage', id, kind: 'paragraph', inlines: plain(text) }) as const

/** One section as the API serves it: three paragraphs under two headings, with its links. */
export function handbookSection(
  persona: keyof typeof HANDBOOK_PERSONAS,
  id: string,
): SectionDetail | null {
  const all = handbookSections(persona)
  const at = all.findIndex((s) => s.id === id)
  if (at < 0) return null
  const s = all[at]!
  const link = (x: SectionSummary | undefined) => (x ? { id: x.id, title: x.title } : null)
  const suffix = id.replace(/^[A-Z]{2}-/, '')
  return {
    ...s,
    blocks: [
      { type: 'heading', level: 2, text: 'How much you receive' },
      para('p1', `The first paragraph of ${id}.`),
      { type: 'heading', level: 2, text: 'When you can use it' },
      para('p2', `The second paragraph of ${id}.`),
      para('p3', `The third paragraph of ${id}.`),
    ],
    sources: s.kind === 'addendum' ? [SOURCES[s.addendumState!]!] : [],
    supplements:
      s.kind === 'addendum' ? ref(all.find((x) => x.kind === 'company' && x.id === suffix)!) : null,
    supplementedBy:
      s.kind === 'company'
        ? all.filter((x) => x.kind === 'addendum' && x.id.endsWith(`-${id}`)).map(ref)
        : [],
    previous: link(all[at - 1]),
    next: link(all[at + 1]),
  } as SectionDetail
}

/** A search result for a section, with the match marked in an excerpt. */
export function searchResult(
  section: SectionSummary,
  before: string,
  match: string,
  after: string,
  passageId = 'p1',
): SearchResultOut {
  return {
    section,
    passageId,
    excerpt: [
      { text: before, match: false },
      { text: match, match: true },
      { text: after, match: false },
    ],
  }
}

type Options = {
  /** What the search returns for a query; the default finds no one. */
  search?: (q: string, sections: SectionSummary[]) => SearchResultOut[]
}

/** Serves the handbook list and search for a persona, and records the search requests. */
export function installFakeHandbook(
  persona: keyof typeof HANDBOOK_PERSONAS,
  { search = () => [] }: Options = {},
) {
  const searches: string[] = []
  const heldSearches = new Map<string, Promise<void>>()
  const failingSearches = new Set<string>()
  const heldSections = new Map<string, Promise<void>>()
  const sectionRequests: string[] = []
  let overviewStatus: number | null = null
  let delayOverview: Promise<void> | null = null
  const sections = handbookSections(persona)
  server.use(
    http.get(url('/api/v1/handbook'), async () => {
      if (delayOverview) await delayOverview
      if (overviewStatus !== null) {
        return HttpResponse.json(
          { type: 'about:blank', title: 'Failure', status: overviewStatus, instance: '/' },
          { status: overviewStatus },
        )
      }
      return HttpResponse.json(handbookOverview(persona))
    }),
    http.get(url('/api/v1/handbook/sections/:id'), async ({ params }) => {
      const id = decodeURIComponent(String(params.id))
      sectionRequests.push(id)
      await heldSections.get(id)
      const section = handbookSection(persona, id)
      return section
        ? HttpResponse.json(section)
        : HttpResponse.json(
            { type: 'about:blank', title: 'Not found', status: 404, instance: '/' },
            { status: 404 },
          )
    }),
    http.get(url('/api/v1/handbook/search'), async ({ request }) => {
      const q = new URL(request.url).searchParams.get('q') ?? ''
      searches.push(q)
      await heldSearches.get(q)
      if (failingSearches.has(q)) {
        return HttpResponse.json(
          { type: 'about:blank', title: 'Failure', status: 500, instance: '/' },
          { status: 500 },
        )
      }
      return HttpResponse.json({ results: search(q, sections) })
    }),
  )
  return {
    sections,
    /** Every search request's `q`, in order. */
    searches: () => searches,
    /** Every section request's ID, in order. */
    sectionRequests: () => sectionRequests,
    /** Hold the answer for this section until the returned function is called. */
    holdSection: (id: string) => {
      let release!: () => void
      heldSections.set(
        id,
        new Promise<void>((resolve) => {
          release = resolve
        }),
      )
      return release
    },
    /** Hold the answer to this search until the returned function is called. */
    holdSearch: (q: string) => {
      let release!: () => void
      heldSearches.set(
        q,
        new Promise<void>((resolve) => {
          release = resolve
        }),
      )
      return release
    },
    /** Make this search answer 500, or work again with `false`. */
    failSearch: (q: string, failing = true) => {
      if (failing) failingSearches.add(q)
      else failingSearches.delete(q)
    },
    /** Make the list answer this status, or work again with null. */
    failOverview: (status: number | null) => {
      overviewStatus = status
    },
    /** Hold the list's answer until the returned function is called. */
    holdOverview: () => {
      let release!: () => void
      delayOverview = new Promise<void>((resolve) => {
        release = resolve
      })
      return release
    },
  }
}
