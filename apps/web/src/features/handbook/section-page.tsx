import { ArrowLeft, ArrowRight, Info } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import type { SectionDetail, SectionLink } from '@/api/generated'
import { useMe } from '@/app/useMe'
import { PageHeader } from '@/components/core/page-header'
import { LoadingStatus } from '@/components/feedback/loading-status'
import { FullPageMessage } from '@/components/feedback/full-page-message'
import { ApplicabilityBadge } from '@/components/handbook/applicability-badge'
import { AppliesMarker } from '@/components/handbook/applies-marker'
import { ChapterNav } from '@/components/handbook/chapter-nav'
import { HandbookBlocks } from '@/components/handbook/handbook-blocks'
import {
  handbookCopy,
  handbookPath,
  notApplicableNote,
  sectionEyebrow,
  sectionNumber,
  stateRulesNote,
} from '@/components/handbook/labels'
import { LastUpdated } from '@/components/handbook/last-updated'
import { LinkBlock } from '@/components/handbook/link-block'
import { SourcesBlock } from '@/components/handbook/sources-block'
import { rowFocusRing } from '@/components/ui/focus-ring'
import { Skeleton } from '@/components/ui/skeleton'
import { PageSandboxIndicator } from '@/features/shell/page-sandbox-indicator'
import { cn } from '@/lib/utils'
import { useClearPassage } from './url-state'
import { useHandbook } from './use-handbook'
import { useSection } from './use-section'

// One handbook section at /handbook/:sectionId, from docs/design/screens/06-handbook. The shell
// supplies the page's one <main>. `?passage=` is a deep link from a citation: the page scrolls to
// that passage, highlights it, and moves focus to it, once.

const PAGE_PADDING =
  'flex min-w-0 flex-col px-14 pt-10 pb-12 max-[1100px]:px-12 max-[760px]:px-5 max-[760px]:pb-8'
// The article and its navigator. Under 1100 px the navigator drops below the article, out of the way.
const LAYOUT =
  'mt-8 grid grid-cols-[minmax(0,var(--spacing-content))_220px] justify-start gap-x-18 max-[1100px]:grid-cols-1 max-[1100px]:gap-y-10'

export function SectionPage() {
  const { sectionId = '' } = useParams()
  const section = useSection(sectionId)
  const overview = useHandbook()
  const [params] = useSearchParams()
  const passageId = params.get('passage') ?? undefined
  const clearPassage = useClearPassage()

  // Focus moves to the cited passage once per section and passage, after the section has
  // rendered. HandbookBlocks re-runs its scroll-and-focus effect when its blocks change, and a
  // refetch can change them; once handled, this turns `focusCited` off so a refetch can't pull
  // focus back from wherever the reader has gone. Clearing the passage lets a later one focus.
  const key = passageId === undefined ? null : `${sectionId}:${passageId}`
  const [handled, setHandled] = useState<string | null>(null)
  const focusCited = key !== null && section.data !== undefined && handled !== key
  if (key === null && handled !== null) setHandled(null)

  if (section.missing) {
    return (
      <MissingSection sectionId={sectionId} versionLabel={overview.data?.version.label ?? null} />
    )
  }

  const data = section.data
  const group = overview.data?.sections.filter((s) =>
    data?.kind === 'company'
      ? s.kind === 'company' && s.chapter === data.chapter
      : s.kind === 'addendum' && s.addendumState === data?.addendumState,
  )
  const loading = !data

  return (
    <div className={PAGE_PADDING}>
      <PageHeader back={{ to: '/handbook', label: 'Handbook' }} right={<PageSandboxIndicator />} />
      <LoadingStatus loading={loading} text={handbookCopy.loading.section} />
      {data ? (
        <div className={LAYOUT}>
          <article className="min-w-0">
            <Header section={data} />
            <Body
              section={data}
              passageId={passageId}
              focusCited={focusCited}
              onFocused={() => setHandled(key)}
              onClear={clearPassage}
            />
            <PreviousAndNext previous={data.previous} next={data.next} />
          </article>
          <div className="max-[1100px]:order-last">
            {group && (
              <ChapterNav
                section={data}
                sections={group}
                className="sticky top-10 max-[1100px]:static"
              />
            )}
          </div>
        </div>
      ) : (
        <SectionSkeleton />
      )}
    </div>
  )
}

function Header({ section }: { section: SectionDetail }) {
  return (
    <header>
      <p className="m-0 text-ui font-regular text-ink-muted">{sectionEyebrow(section)}</p>
      <h1 className="mt-1.5 text-h1 wrap-break-word text-ink">{section.title}</h1>
      <div className="mt-3.5 flex flex-wrap items-center gap-x-4 gap-y-2">
        <ApplicabilityBadge label={section.audienceLabel} />
        <AppliesMarker applies={section.appliesToMe} />
        <LastUpdated date={section.lastUpdated} className="text-small text-ink-muted" />
      </div>
      <p className="mt-4.5 mb-0 flex items-center gap-2 text-small text-ink-muted">
        <Info aria-hidden="true" className="size-3.5 flex-none" />
        {handbookCopy.demoNotice}
      </p>
    </header>
  )
}

function Body({
  section,
  passageId,
  focusCited,
  onFocused,
  onClear,
}: {
  section: SectionDetail
  passageId: string | undefined
  focusCited: boolean
  onFocused: () => void
  onClear: () => void
}) {
  const { data: me } = useMe()
  const company = section.supplements
  // The neutral note: this section isn't for the reader. It says where they work, and points to
  // the company section the addendum supplements, which is where their own rules are.
  const note = !section.appliesToMe && me
  return (
    <>
      {note && (
        <div
          role="note"
          className="mt-6 flex items-start gap-3 rounded-lg border border-border bg-surface-sunken px-4 py-3 text-body"
        >
          <Info aria-hidden="true" className="mt-0.5 size-4 flex-none text-ink-muted" />
          <div className="flex min-w-0 flex-col gap-0.5">
            <p className="m-0">{notApplicableNote(section, me)}</p>
            {company && (
              <Link
                to={handbookPath(company.id)}
                className="w-fit font-medium text-primary underline underline-offset-2"
              >
                {handbookCopy.seeWhatApplies(company.id, company.title)}
              </Link>
            )}
          </div>
        </div>
      )}
      {section.supplementedBy.length > 0 && (
        <LinkBlock
          variant="stateRules"
          note={stateRulesNote(section.supplementedBy.map((s) => s.id.split('-')[0]!))}
          sections={section.supplementedBy}
          className="mt-6"
        />
      )}
      {company && <LinkBlock variant="supplements" sections={[company]} className="mt-6" />}
      <HandbookBlocks
        blocks={section.blocks}
        citedPassageId={passageId}
        focusCited={focusCited}
        onCitedFocused={onFocused}
        onClearCitation={onClear}
        className="mt-6"
      />
      <SourcesBlock sources={section.sources} />
    </>
  )
}

function PreviousAndNext({
  previous,
  next,
}: {
  previous: SectionLink | null
  next: SectionLink | null
}) {
  if (!previous && !next) return null
  const card = cn(
    'flex min-h-18 flex-1 flex-col justify-center gap-1 rounded-lg border border-border px-4 py-3 text-ink no-underline hover:bg-primary-tint hover:text-ink',
    rowFocusRing,
  )
  return (
    <nav
      aria-label={handbookCopy.previousAndNext}
      className="mt-10 flex gap-4 max-[760px]:flex-col"
    >
      {previous ? (
        <Link to={handbookPath(previous.id)} className={card}>
          <span className="flex items-center gap-2 text-small text-ink-muted">
            <ArrowLeft aria-hidden="true" className="size-3.5" />
            {handbookCopy.previous}
          </span>
          <span className="text-body font-semibold">
            {sectionNumber(previous.id)} {previous.title}
          </span>
        </Link>
      ) : (
        <span aria-hidden="true" className="flex-1 max-[760px]:hidden" />
      )}
      {next ? (
        <Link to={handbookPath(next.id)} className={cn(card, 'items-end text-right')}>
          <span className="flex items-center gap-2 text-small text-ink-muted">
            {handbookCopy.next}
            <ArrowRight aria-hidden="true" className="size-3.5" />
          </span>
          <span className="text-body font-semibold">
            {sectionNumber(next.id)} {next.title}
          </span>
        </Link>
      ) : (
        <span aria-hidden="true" className="flex-1 max-[760px]:hidden" />
      )}
    </nav>
  )
}

// Static bars in the article's shape, then the navigator's. No shimmer, as the list's skeleton.
const BODY_BARS = [
  ['100%', '92%', '86%', '54%'],
  ['100%', '94%', '97%', '74%'],
  ['100%', '84%'],
] as const

function SectionSkeleton() {
  return (
    <div aria-hidden="true" className={LAYOUT}>
      <div className="flex min-w-0 flex-col">
        <Skeleton className="w-30" />
        <Skeleton className="mt-4 h-7 w-65 rounded-md" />
        <Skeleton className="mt-6 w-[50%]" />
        <Skeleton className="mt-5 w-[58%]" />
        {BODY_BARS.map((bars, group) => (
          <div key={group} className="mt-10 flex flex-col gap-4">
            {group > 0 && <Skeleton className="mb-1 w-50" />}
            {bars.map((width, i) => (
              <Skeleton key={i} style={{ width }} />
            ))}
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-3 pt-1 max-[1100px]:hidden">
        <Skeleton className="w-30" />
        <Skeleton className="w-37" />
        <Skeleton className="w-27" />
        <Skeleton className="w-35" />
      </div>
    </div>
  )
}

/** An ID that isn't in the sandbox's handbook version, inside the shell with a way back. */
function MissingSection({
  sectionId,
  versionLabel,
}: {
  sectionId: string
  versionLabel: string | null
}) {
  return (
    <FullPageMessage
      title={handbookCopy.missingTitle}
      body={handbookCopy.missingBody(sectionId, versionLabel)}
    >
      <Link
        to="/handbook"
        className={cn(
          'inline-flex items-center gap-2 rounded-sm text-body font-medium text-primary underline underline-offset-2',
          rowFocusRing,
        )}
      >
        <ArrowLeft aria-hidden="true" className="size-4" />
        {handbookCopy.backToHandbook}
      </Link>
    </FullPageMessage>
  )
}
