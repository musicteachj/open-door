import { useGetHandbookSection } from '@/api/generated'
import { isNotFound } from '@/features/global-states/errors'

/**
 * One section. A 404 is not an error here: `missing` is true and the page shows the
 * missing-section state inside the shell. Any other failure goes to the route's error boundary.
 * The ID is encoded, so an ID from the URL can't reach another path.
 */
export function useSection(sectionId: string) {
  const query = useGetHandbookSection(encodeURIComponent(sectionId), {
    query: { throwOnError: (error) => !isNotFound(error) },
  })
  return { ...query, missing: isNotFound(query.error) }
}
