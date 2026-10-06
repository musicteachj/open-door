import { useLocation } from 'react-router'
import { useState } from 'react'
import { useMe } from '@/app/useMe'
import { DirectoryTable, type DirectoryItem } from '@/components/directory/directory-table'
import { PageHeader } from '@/components/core/page-header'
import { EmptyState } from '@/components/core/empty-state'
import { InlineError } from '@/components/feedback/inline-error'
import { FilterSelect } from '@/components/forms/filter-select'
import { FilterToggle } from '@/components/forms/filter-toggle'
import { SearchField } from '@/components/forms/search-field'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useDirectoryFacets, useDirectoryList } from './use-directory-data'
import { PageSandboxIndicator } from '@/features/shell/page-sandbox-indicator'
import { fromDirectory } from './directory-origin'
import { MAX_SEARCH_LENGTH, useDirectoryParams } from './use-directory-params'

// The directory at /directory, from docs/design/screens/04-directory. The shell supplies the
// sandbox indicator and the page's one <main>. State lives in the URL (use-directory-params); the
// rows are an infinite query and the counts are the facets.

/** The latest value that was not undefined, so a failed reload doesn't blank what was on screen. */
function useLastDefined<T>(value: T | undefined): T | undefined {
  const [kept, setKept] = useState(value)
  // Adjusting state while rendering, as React documents, so there is no render with a stale value.
  if (value !== undefined && value !== kept) setKept(value)
  return value ?? kept
}

export function DirectoryPage() {
  const location = useLocation()
  const { data: me } = useMe()
  const params = useDirectoryParams()
  const list = useDirectoryList(params.apiParams)
  const facetsQuery = useDirectoryFacets(params.apiParams)
  // A failed update has no data under its new key, so the last good results stand in for it.
  const pages = useLastDefined(list.data?.pages)
  const facets = useLastDefined(facetsQuery.data)
  const updateFailed = (list.isError && !list.isFetchNextPageError) || facetsQuery.isError

  const items: DirectoryItem[] = (pages ?? []).flatMap((page) =>
    page.items.map((person) => ({
      id: person.id,
      name: `${person.givenName} ${person.familyName}`,
      title: person.title,
      department: person.department.name,
      location: person.location.name,
      to: `/directory/${encodeURIComponent(person.id)}`,
      linkState: fromDirectory(location.search),
    })),
  )

  const searching = params.q !== ''
  // Counts kept from before a failed update describe the old filters, so they only give the total.
  const narrowed = (searching || params.hasFilters) && !facetsQuery.isError
  const count = facets ? (
    narrowed ? (
      `${facets.matching} of ${facets.total} people`
    ) : (
      `${facets.total} people`
    )
  ) : (
    <Skeleton className="inline-block h-3 w-21" />
  )

  return (
    <div className="flex min-w-0 flex-col px-14 pt-10 pb-12 max-[1100px]:px-12 max-[760px]:px-5 max-[760px]:pb-8">
      <PageHeader title="Directory" count={count} right={<PageSandboxIndicator />} />

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <SearchField
          value={params.searchText}
          onChange={params.setSearchText}
          maxLength={MAX_SEARCH_LENGTH}
        />
        <FilterSelect
          label="Location"
          value={params.location}
          options={facets?.locations ?? []}
          onChange={params.setLocation}
        />
        <FilterSelect
          label="Department"
          value={params.department}
          options={facets?.departments ?? []}
          onChange={params.setDepartment}
        />
        {facets?.myTeam != null && (
          <FilterToggle count={facets.myTeam} pressed={params.myTeam} onChange={params.setMyTeam} />
        )}
        {params.hasFilters && (
          <Button variant="ghost" onClick={params.clearFilters}>
            Clear filters
          </Button>
        )}
      </div>

      {updateFailed && (
        <InlineError
          message="We couldn't update the list."
          onRetry={() => {
            if (list.isError) void list.refetch()
            if (facetsQuery.isError) void facetsQuery.refetch()
          }}
        />
      )}

      <DirectoryTable className="mt-6" items={items} loading={list.isPending} youId={me?.id} />

      {!list.isPending && !list.isError && items.length === 0 && (
        <EmptyState
          message={searching ? `No one matches “${params.q}”.` : 'No one matches these filters.'}
          action={
            searching
              ? { label: 'Clear search', onAction: params.clearSearch }
              : { label: 'Clear filters', onAction: params.clearFilters }
          }
        />
      )}

      {/* While a filter or search update has failed the rows are the old ones, and the failed query
          knows nothing of more pages, so the footer says nothing until Retry succeeds. */}
      {items.length > 0 && !(list.isError && !list.isFetchNextPageError) && (
        <div className="flex flex-col items-center gap-3 pt-7 pb-2">
          {list.hasNextPage ? (
            <>
              {(facets || facetsQuery.isError) && (
                <span className="text-small text-ink-muted tabular-nums">
                  {/* Counts kept from before a failed update belong to the old filters. */}
                  Showing {items.length}
                  {facets && !facetsQuery.isError && ` of ${facets.matching}`}
                </span>
              )}
              <Button
                variant="secondary"
                loading={list.isFetchingNextPage}
                onClick={() => void list.fetchNextPage()}
              >
                Show more
              </Button>
            </>
          ) : (
            items.length > 50 && (
              <p className="m-0 text-small text-ink-muted tabular-nums">
                Showing all {items.length}
              </p>
            )
          )}
          {list.isFetchNextPageError && (
            <InlineError
              message="We couldn't load more people."
              onRetry={() => void list.fetchNextPage()}
            />
          )}
        </div>
      )}
    </div>
  )
}
