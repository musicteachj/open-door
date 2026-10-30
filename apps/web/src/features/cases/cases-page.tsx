import { keepPreviousData } from '@tanstack/react-query'
import { Lock } from 'lucide-react'
import { useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { useMe, type SignedInMe } from '@/app/useMe'
import {
  listCases,
  useListCases,
  type QueueFilter,
  type QueueItemOut,
  type QueuePageOut,
} from '@/api/generated'
import { CaseQueueTable } from '@/components/cases/case-queue-table'
import { pagesCopy, QUEUE_FILTERS, type QueueFilterValue } from '@/components/cases/labels'
import { todayIn } from '@/components/cases/today'
import { PageHeader } from '@/components/core/page-header'
import { LoadingStatus } from '@/components/feedback/loading-status'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { NotFound } from '@/features/global-states/pages'
import { PageSandboxIndicator } from '@/features/shell/page-sandbox-indicator'
import { onlyFirstLoad } from './read-options'

// HR's queue at /cases, from docs/design/screens/12-hr-cases: every case's person, category, and
// reply line, never the words. The filter is in the address (`?status=`), "Open" by default. Only
// HR sees it: anyone else gets the Not found page.

export function CasesPage() {
  const { data: me } = useMe()
  if (!me) return null
  if (!me.isHrAdmin) return <NotFound />
  return <Queue me={me} />
}

const FILTER_VALUES = new Set<string>(QUEUE_FILTERS.map((filter) => filter.value))
const DEFAULT_FILTER: QueueFilterValue = 'open'

function filterOf(param: string | null): QueueFilterValue {
  return param !== null && FILTER_VALUES.has(param) ? (param as QueueFilterValue) : DEFAULT_FILTER
}

function Queue({ me }: { me: SignedInMe }) {
  const [params, setParams] = useSearchParams()
  const filter = filterOf(params.get('status'))
  const first = useListCases(
    { status: filter === 'all' ? undefined : (filter as QueueFilter) },
    // The last filter's rows stay up while the next one loads, so the filter keeps its place
    // (and the person's focus) instead of being swapped for a skeleton.
    { query: { throwOnError: onlyFirstLoad, placeholderData: keepPreviousData } },
  )
  const more = useMorePages(filter, first.data, first.isPlaceholderData)
  const timeZone = me.location.timezone
  const rows: QueueItemOut[] = [...(first.data?.items ?? []), ...more.items]
  const nextCursor = first.isPlaceholderData ? null : more.nextCursor

  return (
    <div className="flex min-w-0 flex-col px-14 pt-10 pb-12 max-[1100px]:px-12 max-[760px]:px-5 max-[760px]:pb-8">
      <div className="w-full max-w-270">
        <PageHeader
          title={pagesCopy.casesTitle}
          icon={<Lock aria-hidden="true" className="size-7 flex-none self-center text-primary" />}
          right={<PageSandboxIndicator />}
        />
        <LoadingStatus loading={!first.data} text={pagesCopy.casesLoading} />
        <p className="m-0 mt-2 max-w-155 text-body-lg text-pretty text-ink-muted">
          {pagesCopy.casesIntro}
        </p>
        <div className="mt-6" aria-busy={first.isPlaceholderData || undefined}>
          {first.data ? (
            <>
              <CaseQueueTable
                rows={rows}
                filter={filter}
                onFilterChange={(next) =>
                  setParams(next === DEFAULT_FILTER ? {} : { status: next }, { replace: true })
                }
                today={todayIn(timeZone)}
                timeZone={timeZone}
              />
              {more.failed && (
                <p role="alert" className="m-0 mt-4 text-ui text-ink-muted">
                  {pagesCopy.loadMoreFailed}
                </p>
              )}
              {nextCursor !== null && (
                <div className="mt-6">
                  <Button
                    variant="secondary"
                    loading={more.loading}
                    onClick={() => void more.load(nextCursor)}
                  >
                    {pagesCopy.loadMore}
                  </Button>
                </div>
              )}
            </>
          ) : (
            <div aria-hidden="true" data-slot="queue-skeleton" className="flex flex-col gap-3">
              <Skeleton className="h-9 w-72" />
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

type MorePages = {
  filter: QueueFilterValue
  /** The first page these follow. A first page whose data changed is a new object, which drops them. */
  after: QueuePageOut | undefined
  items: QueueItemOut[]
  cursor: string | null
}

/**
 * The pages after the first. The first page is a query (so a status change refreshes it); later
 * pages are read on demand and held here. They are dropped when the filter changes or the first
 * page's data changes (its rows may no longer line up with them). A read that finds the same data
 * (a window-focus refetch) keeps them: TanStack Query hands back the same object then. A failed read says so and keeps
 * the button.
 */
function useMorePages(
  filter: QueueFilterValue,
  firstPage: QueuePageOut | undefined,
  placeholder: boolean,
) {
  const [more, setMore] = useState<MorePages | null>(null)
  const [loadingFor, setLoadingFor] = useState<QueueFilterValue | null>(null)
  const [failedFor, setFailedFor] = useState<QueueFilterValue | null>(null)
  // The state above is read from the render closure, so a second click before the page draws
  // again would pass it. The ref is current at once.
  const loadingRef = useRef<QueueFilterValue | null>(null)
  const mine = !placeholder && more?.filter === filter && more.after === firstPage ? more : null
  return {
    items: mine?.items ?? [],
    nextCursor: mine ? mine.cursor : (firstPage?.nextCursor ?? null),
    loading: loadingFor === filter,
    failed: failedFor === filter,
    load: async (cursor: string) => {
      if (loadingRef.current === filter || !firstPage) return
      loadingRef.current = filter
      setLoadingFor(filter)
      setFailedFor(null)
      try {
        const page = await listCases({
          status: filter === 'all' ? undefined : (filter as QueueFilter),
          cursor,
        })
        setMore({
          filter,
          after: firstPage,
          items: [...(mine?.items ?? []), ...page.items],
          cursor: page.nextCursor,
        })
      } catch {
        setFailedFor(filter)
      } finally {
        if (loadingRef.current === filter) loadingRef.current = null
        setLoadingFor((current) => (current === filter ? null : current))
      }
    },
  }
}
