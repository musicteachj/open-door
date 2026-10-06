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
import { PAGE_SIZE, useDirectoryFacets, useDirectoryList } from './use-directory-data'
import { PageSandboxIndicator } from '@/features/shell/page-sandbox-indicator'
import { fromDirectory } from './directory-origin'
import {
  MAX_SEARCH_LENGTH,
  useDirectoryParams,
  type DirectoryApiParams,
} from './use-directory-params'

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

/** The IDs of the options the facets listed. Each sandbox has its own, so a link from another one carries IDs that match nothing here. */
type OptionIds = { locations: ReadonlySet<string>; departments: ReadonlySet<string> }

/** The filters with any location or department that isn't a known option left out. */
function withKnownFilters(api: DirectoryApiParams, known: OptionIds | undefined) {
  const { locationId, departmentId, ...rest } = api
  return {
    ...rest,
    ...(locationId && known?.locations.has(locationId) ? { locationId } : {}),
    ...(departmentId && known?.departments.has(departmentId) ? { departmentId } : {}),
  }
}

export function DirectoryPage() {
  const { data: me } = useMe()
  const params = useDirectoryParams()
  // A location or department in the URL counts only once the facets have said it is one of the
  // options (the URL itself is left alone). Until then the facets are asked without them, and the
  // list waits, so no screen shows "All" menus over a list filtered by a stranger's ID.
  const [known, setKnown] = useState<OptionIds>()
  const unverified = known === undefined && (params.location !== null || params.department !== null)
  const facetParams = withKnownFilters(params.apiParams, known)
  const facetsQuery = useDirectoryFacets(facetParams)
  if (!known && facetsQuery.data) {
    setKnown({
      locations: new Set(facetsQuery.data.locations.map((option) => option.id)),
      departments: new Set(facetsQuery.data.departments.map((option) => option.id)),
    })
  }
  // If the facets cannot say, the URL's location and department are not applied either: the list
  // is by search and team only, as the page says, until Retry succeeds.
  const list = useDirectoryList(facetParams, {
    enabled: !unverified || facetsQuery.isError,
  })
  // A failed update has no data under its new key, so the last good results stand in for it.
  const pages = useLastDefined(list.data?.pages)
  const facets = useLastDefined(facetsQuery.data)
  // The counts failed on the first visit: nothing to show for them, and the list itself is fine.
  const facetsMissing = facetsQuery.isError && !facets
  const updateFailed =
    (list.isError && !list.isFetchNextPageError) || (facetsQuery.isError && !facetsMissing)
  const location = known?.locations.has(params.location ?? '') ? params.location : null
  const department = known?.departments.has(params.department ?? '') ? params.department : null
  const hasFilters = location !== null || department !== null || params.myTeam

  const items: DirectoryItem[] = (pages ?? []).flatMap((page) =>
    page.items.map((person) => ({
      id: person.id,
      name: `${person.givenName} ${person.familyName}`,
      title: person.title,
      department: person.department.name,
      location: person.location.name,
      to: `/directory/${encodeURIComponent(person.id)}`,
      linkState: fromDirectory(params.listSearch),
      onFollow: params.flushSearch,
    })),
  )

  const searching = params.q !== ''
  // Counts kept from before a failed update describe the old filters, so they only give the total.
  const narrowed = (searching || hasFilters) && !facetsQuery.isError
  const count = facetsMissing ? undefined : facets ? (
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
        {!facetsMissing && (
          <>
            <FilterSelect
              label="Location"
              value={location}
              options={facets?.locations ?? []}
              onChange={params.setLocation}
            />
            <FilterSelect
              label="Department"
              value={department}
              options={facets?.departments ?? []}
              onChange={params.setDepartment}
            />
          </>
        )}
        {facets?.myTeam != null && (
          <FilterToggle count={facets.myTeam} pressed={params.myTeam} onChange={params.setMyTeam} />
        )}
        {hasFilters && (
          <Button variant="ghost" onClick={params.clearFilters}>
            Clear filters
          </Button>
        )}
      </div>

      {facetsMissing && (
        <InlineError
          message="We couldn't load the filters."
          onRetry={() => void facetsQuery.refetch()}
        />
      )}

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
            items.length > PAGE_SIZE && (
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
