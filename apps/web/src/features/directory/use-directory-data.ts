import { keepPreviousData, useInfiniteQuery, useQueryClient } from '@tanstack/react-query'
import { listPeople, useGetDirectoryFacets } from '@/api/generated'
import type { DirectoryApiParams } from './use-directory-params'

/** The API's page size for the directory. */
export const PAGE_SIZE = 50

const LIST_KEY = ['/api/v1/people', 'pages'] as const

// The list is the page. If it fails before any list has been shown, the failure goes to the route's
// error boundary, which renders "Something went wrong" inside the shell, even when the counts have
// arrived. Once a list has been shown, a failed update keeps what is on screen and the page says so
// inline. The counts never throw: they are an accessory, so their failing (first load or later)
// keeps the rows and shows the inline alert, however the two requests happen to be ordered. If both
// fail on the first load, the list's failure is the one that throws. The cache holds no one else's
// data: a switch or sign-out clears it.
function useThrowBeforeFirstList() {
  const queryClient = useQueryClient()
  return () =>
    !queryClient.getQueriesData({ queryKey: LIST_KEY }).some(([, data]) => data !== undefined)
}

/**
 * The directory's rows, a page at a time. The filters are in the key, so changing one starts a new
 * query at page one rather than adding to the old pages. The previous results stay on screen
 * while the new ones load. The key holds no identity: a switch or sign-out clears the whole cache.
 */
export function useDirectoryList(params: DirectoryApiParams, { enabled = true } = {}) {
  const throwOnError = useThrowBeforeFirstList()
  return useInfiniteQuery({
    queryKey: [...LIST_KEY, params],
    queryFn: ({ pageParam, signal }) =>
      listPeople(
        { ...params, limit: PAGE_SIZE, ...(pageParam ? { cursor: pageParam } : {}) },
        { signal },
      ),
    initialPageParam: '',
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    placeholderData: keepPreviousData,
    throwOnError,
    enabled,
  })
}

/** The counts for the header and the filter menus, under the same filters as the list. */
export function useDirectoryFacets(params: DirectoryApiParams) {
  return useGetDirectoryFacets(params, {
    query: { placeholderData: keepPreviousData },
  })
}
