import { useQueryClient, type QueryKey } from '@tanstack/react-query'
import { type HandbookOverview, getGetHandbookQueryKey, useGetHandbook } from '@/api/generated'

const HOME_KEY = getGetHandbookQueryKey()
const SECTION_KEY: QueryKey = [...HOME_KEY, 'section']

/**
 * The handbook's version, chapter names, and every section of the sandbox's pinned version, each
 * with whether it applies to the signed-in person (worked out on the server). The list is the
 * page: a failure goes to the route's error boundary, which shows "Something went wrong" inside
 * the shell.
 */
export function useHandbook() {
  return useGetHandbook({ query: { throwOnError: true, ...useSeedFrom(SECTION_KEY) } })
}

/**
 * The same overview for the section page, which needs it only for the chapter navigator and the
 * version label. A failure leaves them out instead of replacing the section with the error page.
 * It has its own cache entry, so an error left in it can't reach the handbook home, which throws
 * (an observer that throws on errors doesn't retry a cached one when it mounts).
 */
export function useHandbookForSection() {
  return useGetHandbook({ query: { queryKey: SECTION_KEY, ...useSeedFrom(HOME_KEY) } })
}

// Each entry starts from the other's data, so moving between the list and a section shows the
// overview at once while it is fetched again. Only data is copied, never an error.
function useSeedFrom(key: QueryKey) {
  const client = useQueryClient()
  return {
    initialData: () => client.getQueryData<HandbookOverview>(key),
    initialDataUpdatedAt: () => client.getQueryState(key)?.dataUpdatedAt,
  }
}
