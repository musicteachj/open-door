import { keepPreviousData } from '@tanstack/react-query'
import { useSearchHandbook } from '@/api/generated'
import { MAX_SEARCH_LENGTH } from './url-state'

/**
 * The search results for a query. It runs only for a non-empty trimmed query, and asks for at most
 * 100 characters. The previous results stay on screen while the next ones load.
 */
export function useHandbookSearch(query: string) {
  const q = query.trim().slice(0, MAX_SEARCH_LENGTH)
  return useSearchHandbook(
    { q },
    { query: { enabled: q !== '', placeholderData: keepPreviousData } },
  )
}
