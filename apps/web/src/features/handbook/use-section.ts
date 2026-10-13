import { useGetHandbookSection } from '@/api/generated'
import { isNotFound } from '@/features/global-states/errors'
import { isPathSegment } from './path-segment'

/**
 * One section. A 404 is not an error here: `missing` is true and the page shows the
 * missing-section state inside the shell. Any other failure goes to the route's error boundary.
 * The ID is encoded, and "." or ".." is missing without a request, so an ID from the URL can't
 * reach another path.
 */
export function useSection(sectionId: string) {
  const sendable = isPathSegment(sectionId)
  const query = useGetHandbookSection(encodeURIComponent(sectionId), {
    query: { enabled: sendable, throwOnError: (error) => !isNotFound(error) },
  })
  return { ...query, missing: !sendable || isNotFound(query.error) }
}
