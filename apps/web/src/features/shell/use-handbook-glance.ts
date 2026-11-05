import { getGetHandbookQueryKey, useGetHandbook } from '@/api/generated'

/** The handbook changes rarely, so a read this recent is reused by whoever asks next. */
const HANDBOOK_STALE_MS = 5 * 60_000

/**
 * The handbook for the places that only decorate with it: the rail's "Handbook updated" figure and
 * the console's section titles. It has its own cache entry, shared by those two and not by the
 * Handbook page: that page's query throws to the error page, and a failure here must not be left
 * in its entry for the page to find. A failure leaves the figure or the titles out.
 */
export function useHandbookGlance(enabled = true) {
  return useGetHandbook({
    query: {
      queryKey: [...getGetHandbookQueryKey(), 'glance'],
      enabled,
      staleTime: HANDBOOK_STALE_MS,
    },
  })
}
