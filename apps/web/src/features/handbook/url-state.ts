import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useSearchParams } from 'react-router'

/** The pause after the last keystroke before the search is written to the URL. */
export const SEARCH_PAUSE_MS = 250
/** The longest search the API takes. The search box stops here too. */
export const MAX_SEARCH_LENGTH = 100

export type ShowFilter = 'all' | 'mine'

// The character classes the API's clean_query turns into spaces.
const DROPPED = /[\p{Cc}\p{Cf}\p{Cs}\p{Co}\p{Cn}]/gu

/**
 * The handbook home's state, kept in the URL so it can be shared and Back works: `q` and
 * `show=mine`. An unset value is absent from the URL.
 *
 * History: a search replaces the entry, so typing leaves no trail of half-typed words. A change of
 * the Show filter pushes one, so Back undoes it. The typed text is shown at once and written to
 * the URL after a 250 ms pause, the same rules as the directory's search.
 */
export function useHandbookParams() {
  const [searchParams, setSearchParams] = useSearchParams()
  const locationKey = useLocation().key
  // As the API does, control, format, surrogate, private-use and unassigned characters become
  // spaces, so a query of nothing else is no search rather than one the API refuses.
  const q = (searchParams.get('q') ?? '').replace(DROPPED, ' ').replace(/\s+/g, ' ').trim()
  const show: ShowFilter = searchParams.get('show') === 'mine' ? 'mine' : 'all'

  // Writes build on the latest URL, not the one this render saw, so a write that follows another
  // before React re-renders keeps both.
  const latest = useRef(searchParams)
  useEffect(() => {
    latest.current = searchParams
  }, [searchParams])

  // Whether a navigation this hook just made is still to be seen.
  const ownNavigation = useRef(false)
  const write = useCallback(
    (change: Record<string, string | null>, replace: boolean) => {
      const next = new URLSearchParams(latest.current)
      for (const [key, value] of Object.entries(change)) {
        if (value === null || value === '') next.delete(key)
        else next.set(key, value)
      }
      latest.current = next
      ownNavigation.current = true
      setSearchParams(next, { replace })
    },
    [setSearchParams],
  )

  // The text in the box leads the URL's `q` by the pause, and follows it when the URL changes some
  // other way (Back, a link).
  const queryText = q.slice(0, MAX_SEARCH_LENGTH)
  const [searchText, setSearchText] = useState(queryText)
  // The latest typed text, and whether its write is still waiting, for a flush between renders.
  const typed = useRef(searchText)
  const waiting = useRef(false)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const cancelPending = useCallback(() => {
    clearTimeout(timer.current)
    waiting.current = false
  }, [])
  // A navigation the hook didn't make would have a write still waiting put the typed text onto
  // that page. So a new location key that isn't the hook's own drops the write, and the box
  // follows the URL.
  const seenKey = useRef(locationKey)
  useEffect(() => {
    if (seenKey.current === locationKey) return
    seenKey.current = locationKey
    if (ownNavigation.current) {
      ownNavigation.current = false
      return
    }
    cancelPending()
    setSearchText(queryText)
  }, [locationKey, queryText, cancelPending])
  useEffect(() => cancelPending, [cancelPending])

  const onSearchText = useCallback(
    (text: string) => {
      typed.current = text
      setSearchText(text)
      cancelPending()
      waiting.current = true
      timer.current = setTimeout(() => {
        waiting.current = false
        write({ q: text.trim() }, true)
      }, SEARCH_PAUSE_MS)
    },
    [cancelPending, write],
  )

  // Following a result unmounts the page, which drops a write still waiting, and Back would come
  // to a list without the typed text. So the link writes it first, onto the entry Back returns to.
  const flushSearch = useCallback(() => {
    if (!waiting.current) return
    cancelPending()
    write({ q: typed.current.trim() }, true)
  }, [cancelPending, write])

  const clearSearch = useCallback(() => {
    cancelPending()
    typed.current = ''
    setSearchText('')
    write({ q: null }, true)
  }, [cancelPending, write])

  // A search still waiting is written first, onto the current entry, so Back undoes only the filter.
  const setShow = useCallback(
    (next: ShowFilter) => {
      flushSearch()
      write({ show: next === 'mine' ? 'mine' : null }, false)
    },
    [flushSearch, write],
  )

  return {
    q,
    /** The search as the API takes it: at most 100 characters. */
    queryText,
    searchText,
    setSearchText: onSearchText,
    clearSearch,
    flushSearch,
    show,
    setShow,
  }
}

/**
 * "Clear highlight": removes `passage` from the URL, replacing the history entry so Back doesn't
 * return to the highlight. Everything else in the URL stays.
 */
export function useClearPassage() {
  const [, setSearchParams] = useSearchParams()
  return useCallback(() => {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current)
        next.delete('passage')
        return next
      },
      { replace: true },
    )
  }, [setSearchParams])
}
