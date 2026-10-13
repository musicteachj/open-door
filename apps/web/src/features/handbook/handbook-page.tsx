import { ArrowRight, Info } from 'lucide-react'
import { useRef } from 'react'
import type { HandbookOverview, SearchResultOut, SectionSummary } from '@/api/generated'
import { PageSandboxIndicator } from '@/features/shell/page-sandbox-indicator'
import { FilterSelect } from '@/components/forms/filter-select'
import { SearchField } from '@/components/forms/search-field'
import { InlineError } from '@/components/feedback/inline-error'
import { LoadingStatus } from '@/components/feedback/loading-status'
import { SearchResultRow } from '@/components/handbook/search-result-row'
import { SectionGroup } from '@/components/handbook/section-group'
import { SectionRow, sectionColumns } from '@/components/handbook/section-row'
import { addendumGroupNote, handbookCopy } from '@/components/handbook/labels'
import { EmptyState } from '@/components/core/empty-state'
import { Skeleton } from '@/components/ui/skeleton'
import { formatShortDate } from '@/lib/time'
import { cn } from '@/lib/utils'
import { MAX_SEARCH_LENGTH, useHandbookParams, type ShowFilter } from './url-state'
import { useAskAssistant } from './use-ask-assistant'
import { useHandbook } from './use-handbook'
import { useHandbookSearch } from './use-handbook-search'

// The handbook home at /handbook, from docs/design/screens/06-handbook. The shell supplies the
// sandbox indicator's place and the page's one <main>. `q` and `show` live in the URL
// (url-state.ts). The list is one request; the search is another, and runs only with text.

const COMPANY = 'Juniper Row'
const SHOW_APPLIES: ShowFilter = 'mine'

/** The sections of a chapter or addendum, kept in the order the API listed them. */
type Group = { id: string; num: string; title: string; note?: string; sections: SectionSummary[] }

/** Chapters in number order, then addenda in the API's order, leaving out any with no sections. */
function groupSections(overview: HandbookOverview, sections: SectionSummary[]) {
  const chapters: Group[] = Object.entries(overview.chapters)
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([num, title]) => ({
      id: `chapter-${num}`,
      num,
      title,
      sections: sections.filter((s) => s.kind === 'company' && s.chapter === Number(num)),
    }))
  const addenda: Group[] = Object.entries(overview.addenda).map(([code, title]) => ({
    id: `addendum-${code}`,
    num: code,
    title,
    note: addendumGroupNote(code),
    sections: sections.filter((s) => s.kind === 'addendum' && s.addendumState === code),
  }))
  return {
    chapters: chapters.filter((g) => g.sections.length > 0),
    addenda: addenda.filter((g) => g.sections.length > 0),
  }
}

export function HandbookPage() {
  const params = useHandbookParams()
  const overview = useHandbook()
  const searching = params.queryText !== ''
  const sections = overview.data?.sections
  const mine = params.show === SHOW_APPLIES
  // One list serves the menu's count and the "Applies to me" view, so the two can't disagree.
  const applying = sections?.filter((s) => s.appliesToMe)
  const shown = mine ? applying : sections
  const toolbar = useRef<HTMLDivElement>(null)
  // The search field is a shared component with no ref to hand out, so the toolbar finds its input.
  const clearSearchAndFocus = () => {
    params.clearSearch()
    toolbar.current?.querySelector('input')?.focus()
  }

  return (
    <div className="flex min-w-0 flex-col px-14 pt-10 pb-12 max-[1100px]:px-12 max-[760px]:px-5 max-[760px]:pb-8">
      <header className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-h1 wrap-break-word text-ink">{handbookCopy.title}</h1>
          {overview.data ? (
            <p className="m-0 text-ui text-ink-muted tabular-nums">
              {COMPANY} · Version {overview.data.version.label} · Updated{' '}
              {formatShortDate(overview.data.version.updatedOn)}
            </p>
          ) : (
            // Keeps the line's place, so the page doesn't jump when the version arrives.
            <div aria-hidden="true" className="flex h-5 items-center">
              <Skeleton className="w-80 max-w-full" />
            </div>
          )}
        </div>
        <PageSandboxIndicator />
      </header>

      <p className="mt-4 mb-0 flex items-center gap-2 text-small text-ink-muted">
        <Info aria-hidden="true" className="size-3.5 flex-none" />
        {handbookCopy.demoNotice}
      </p>

      <div ref={toolbar} className="mt-6 flex flex-wrap items-center gap-3">
        <SearchField
          value={params.searchText}
          onChange={params.setSearchText}
          maxLength={MAX_SEARCH_LENGTH}
          label={handbookCopy.searchLabel}
          placeholder={handbookCopy.searchLabel}
          className="w-90"
        />
        <FilterSelect
          label="Show"
          value={mine ? SHOW_APPLIES : null}
          allLabel={handbookCopy.filterAll}
          allCount={sections?.length ?? 0}
          options={[
            {
              id: SHOW_APPLIES,
              name: handbookCopy.filterApplies,
              count: applying?.length ?? 0,
            },
          ]}
          onChange={(id) => params.setShow(id === SHOW_APPLIES ? 'mine' : 'all')}
        />
      </div>

      {searching ? (
        <Results
          text={params.queryText}
          mine={mine}
          onClear={clearSearchAndFocus}
          onShowAll={() => params.setShow('all')}
          onFollow={params.flushSearch}
        />
      ) : (
        <SectionList overview={overview.data} sections={shown} />
      )}
    </div>
  )
}

/** The labels over the columns. Visual only, as in the directory: each row's name says it all. */
function ColumnLabels() {
  return (
    <div className="@container">
      <div
        aria-hidden="true"
        className={cn(
          sectionColumns,
          'h-10 border-b border-border text-small text-ink-muted @max-[56rem]:hidden',
        )}
      >
        <span className="col-span-2">{handbookCopy.columns.section}</span>
        <span>{handbookCopy.columns.appliesTo}</span>
        <span />
        <span>{handbookCopy.columns.lastUpdated}</span>
        <span />
      </div>
    </div>
  )
}

function SectionList({
  overview,
  sections,
}: {
  overview: HandbookOverview | undefined
  sections: SectionSummary[] | undefined
}) {
  const loading = !overview || !sections
  const groups = loading ? null : groupSections(overview, sections)
  return (
    <div className="mt-6" aria-busy={loading}>
      <LoadingStatus loading={loading} text={handbookCopy.loading.handbook} />
      <ColumnLabels />
      {groups ? (
        <>
          {groups.chapters.map((group) => (
            <Rows key={group.id} group={group} />
          ))}
          {groups.addenda.length > 0 && (
            <>
              <div className="mt-12 flex flex-wrap items-baseline gap-x-3 px-3">
                <h2 className="text-h2">{handbookCopy.addendaHeading}</h2>
                <span className="text-ui text-ink-muted">{handbookCopy.addendaNote}</span>
              </div>
              {groups.addenda.map((group) => (
                <Rows key={group.id} group={group} />
              ))}
            </>
          )}
        </>
      ) : (
        <ListSkeleton />
      )}
    </div>
  )
}

function Rows({ group }: { group: Group }) {
  return (
    <SectionGroup id={group.id} num={group.num} title={group.title} note={group.note}>
      {group.sections.map((section) => (
        <SectionRow key={section.id} section={section} />
      ))}
    </SectionGroup>
  )
}

// Three static groups, as in the design: a heading's bars, then rows. No shimmer.
const SKELETON_GROUPS = [
  {
    title: '30%',
    rows: [
      ['42%', '56%'],
      ['34%', '64%'],
      ['48%', '52%'],
    ],
  },
  {
    title: '42%',
    rows: [
      ['36%', '48%'],
      ['50%', '60%'],
      ['40%', '48%'],
      ['46%', '56%'],
    ],
  },
  {
    title: '36%',
    rows: [
      ['30%', '56%'],
      ['44%', '52%'],
      ['38%', '60%'],
      ['52%', '48%'],
    ],
  },
] as const

function ListSkeleton() {
  return (
    <div aria-hidden="true">
      {SKELETON_GROUPS.map((group, g) => (
        <div key={g}>
          <div className="grid h-15.5 grid-cols-[72px_minmax(0,1fr)] items-center gap-x-5 border-b border-border px-3">
            <Skeleton className="mb-4 w-4 self-end" />
            <Skeleton className="mb-4 self-end" style={{ width: group.title }} />
          </div>
          {group.rows.map(([title, applies], r) => (
            <div
              key={r}
              className={cn(
                sectionColumns,
                'h-12 border-b border-border-subtle @max-[56rem]:hidden',
              )}
            >
              <Skeleton className="w-7" />
              <Skeleton style={{ width: title }} />
              <Skeleton style={{ width: applies }} />
              <span />
              <Skeleton className="w-21" />
              <span />
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

function Results({
  text,
  mine,
  onClear,
  onShowAll,
  onFollow,
}: {
  text: string
  mine: boolean
  onClear: () => void
  onShowAll: () => void
  onFollow: () => void
}) {
  const search = useHandbookSearch(text)
  const askAssistant = useAskAssistant()
  const all: SearchResultOut[] | undefined = search.data?.results
  // The API puts the sections that apply first. "Applies to me" keeps just those.
  const results = mine ? all?.filter((r) => r.section.appliesToMe) : all
  // The previous query's results stay in `data` while the new ones load. They are not this
  // query's: they are shown dimmed, with no count and no "no results" claim.
  const stale = search.isPlaceholderData

  if (search.isError && !results) {
    return (
      <InlineError
        message="We couldn't search the handbook."
        onRetry={() => void search.refetch()}
      />
    )
  }
  if (!results || (stale && results.length === 0)) {
    return (
      <div className="mt-6" aria-busy="true">
        <LoadingStatus loading text="Searching the handbook" />
        <div aria-hidden="true" className="flex flex-col">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex flex-col gap-3 border-b border-border-subtle px-3 py-5">
              <Skeleton className="w-1/4" />
              <Skeleton className="w-3/4" />
            </div>
          ))}
        </div>
      </div>
    )
  }
  const ask = {
    label: handbookCopy.askAssistant,
    onAction: () => askAssistant(text),
    icon: <ArrowRight aria-hidden="true" className="size-4" />,
  }
  if (results.length === 0) {
    // Matches exist but none apply to this person: say so, and offer the way to see them.
    const noneApply = mine && all !== undefined && all.length > 0
    return noneApply ? (
      <EmptyState
        message={handbookCopy.noneApplyMatch(text)}
        action={{ label: handbookCopy.showAllSections, onAction: onShowAll }}
        secondaryAction={ask}
      />
    ) : (
      <EmptyState
        message={handbookCopy.noMatch(text)}
        action={{ label: handbookCopy.clearSearch, onAction: onClear }}
        secondaryAction={ask}
      />
    )
  }
  return (
    <div className="mt-6">
      {search.isError && (
        <InlineError
          message="We couldn't update the results."
          onRetry={() => void search.refetch()}
        />
      )}
      {stale ? (
        <LoadingStatus loading text="Searching the handbook" />
      ) : (
        <output className="block border-b border-border px-3 pb-3 text-ui text-ink-muted">
          {results.length === 1
            ? `1 section matches “${text}”`
            : `${results.length} sections match “${text}”`}
        </output>
      )}
      <ul
        className={cn('m-0 list-none p-0', stale && 'opacity-60')}
        aria-label="Search results"
        aria-busy={stale}
      >
        {results.map((result) => (
          <SearchResultRow
            key={`${result.section.id}-${result.passageId}`}
            result={result}
            onNavigate={onFollow}
          />
        ))}
      </ul>
    </div>
  )
}
