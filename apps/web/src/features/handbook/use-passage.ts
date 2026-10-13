import { useGetHandbookPassage } from '@/api/generated'

/**
 * One passage with its neighbors, for the passage panel. It runs only when both IDs are given.
 * The IDs are encoded, so one from the URL can't reach another path.
 */
export function usePassage(sectionId: string | null, passageId: string | null) {
  return useGetHandbookPassage(
    encodeURIComponent(sectionId ?? ''),
    encodeURIComponent(passageId ?? ''),
    { query: { enabled: Boolean(sectionId && passageId) } },
  )
}
