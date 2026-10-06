import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useSearchParams } from 'react-router'
import type { ListPeopleParams } from '@/api/generated'
import { isUuid } from '@/lib/uuid'

/** The pause after the last keystroke before the search is written to the URL. */
export const SEARCH_PAUSE_MS = 250
/** The longest search the API takes. The search box stops here too. */
export const MAX_SEARCH_LENGTH = 100

const uuidOrNull = (value: string | null) => (value !== null && isUuid(value) ? value : null)

/** The directory's filters as the API takes them. A filter that isn't set is left out. */
export type DirectoryApiParams = Pick<
  ListPeopleParams,
  'q' | 'locationId' | 'departmentId' | 'team'
>

/**
 * The directory's state, kept in the URL so it can be shared and Back works: `q`, `location`,
 * `department`, and `team=mine`. An unset filter is absent from the URL, never "null" or empty,
 * and so absent from the API request too (the generated client would send `null` as the string
 * "null").
 *
 * History: a search replaces the entry, so typing a name leaves no trail of half-typed words. A
 * filter change pushes one, so Back undoes it. The search text is shown at once and written to the
 * URL after a 250 ms pause.
 */
export function useDirectoryParams() {
  const [searchParams, setSearchParams] = useSearchParams()
  const locationKey = useLocation().key
  // The API refuses a NUL (Postgres can't store one), so it never goes further than the URL.
  const q = (searchParams.get('q') ?? '').replaceAll('\0', '').trim()
  // A filter that isn't a UUID (a mistyped or cut-off link) is no filter: the API answers it with
  // a 422. The URL is left as it is; choosing a filter or clearing writes over it.
  const location = uuidOrNull(searchParams.get('location'))
  const department = uuidOrNull(searchParams.get('department'))
  const myTeam = searchParams.get('team') === 'mine'

  // Writes build on the latest URL, not the one this render saw, so a write that follows another
  // before React re-renders (and a search write that fires after a filter change) keeps both.
  const latest = useRef(searchParams)
  useEffect(() => {
    latest.current = searchParams
  }, [searchParams])

  // Whether a navigation this hook just made (a search or a filter write) is still to be seen.
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

  // The text in the box. It leads the URL's `q` by the pause, and follows it when the URL changes
  // some other way (Back, a link).
  const [searchText, setSearchText] = useState(q)
  // The latest typed text, for a flush that runs between renders.
  const searchTextRef = useRef(searchText)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const waiting = useRef(false)
  const cancelPending = useCallback(() => {
    clearTimeout(timer.current)
    waiting.current = false
  }, [])
  // A navigation the hook didn't make (Back, Forward, a link to /directory), even to a URL with the
  // same search, would have a write still waiting put the typed text onto that page. So a new
  // location key that isn't the hook's own drops the write, and the box follows the URL.
  const seenKey = useRef(locationKey)
  useEffect(() => {
    if (seenKey.current === locationKey) return
    seenKey.current = locationKey
    if (ownNavigation.current) {
      ownNavigation.current = false
      return
    }
    cancelPending()
    setSearchText(q)
  }, [locationKey, q, cancelPending])
  useEffect(() => cancelPending, [cancelPending])

  const writeSearch = useCallback(
    (text: string) => {
      write({ q: text.trim() }, true)
    },
    [write],
  )

  const onSearchText = useCallback(
    (text: string) => {
      searchTextRef.current = text
      setSearchText(text)
      cancelPending()
      waiting.current = true
      timer.current = setTimeout(() => {
        waiting.current = false
        writeSearch(text)
      }, SEARCH_PAUSE_MS)
    },
    [cancelPending, writeSearch],
  )

  // Following a row unmounts the page, which drops a write still waiting, and Back would come to a
  // list without the typed text. So the row writes it first, onto the entry Back returns to.
  const flushSearch = useCallback(() => {
    if (!waiting.current) return
    cancelPending()
    writeSearch(searchTextRef.current)
  }, [cancelPending, writeSearch])

  const clearSearch = useCallback(() => {
    cancelPending()
    setSearchText('')
    writeSearch('')
  }, [cancelPending, writeSearch])

  const apiParams = useMemo<DirectoryApiParams>(
    () => ({
      ...(q ? { q: q.slice(0, MAX_SEARCH_LENGTH) } : {}),
      ...(location ? { locationId: location } : {}),
      ...(department ? { departmentId: department } : {}),
      ...(myTeam ? { team: 'mine' as const } : {}),
    }),
    [q, location, department, myTeam],
  )

  return {
    q,
    searchText,
    setSearchText: onSearchText,
    clearSearch,
    flushSearch,
    /** The list's query string as it will be once the typed search is written: for a row's link. */
    listSearch: (() => {
      const next = new URLSearchParams(searchParams)
      const typed = searchText.replaceAll('\0', '').trim()
      if (typed) next.set('q', typed)
      else next.delete('q')
      const text = next.toString()
      return text ? `?${text}` : ''
    })(),
    location,
    department,
    myTeam,
    setLocation: (id: string | null) => write({ location: id }, false),
    setDepartment: (id: string | null) => write({ department: id }, false),
    setMyTeam: (on: boolean) => write({ team: on ? 'mine' : null }, false),
    /** Resets every filter and leaves the search. */
    clearFilters: () => write({ location: null, department: null, team: null }, false),
    hasFilters: location !== null || department !== null || myTeam,
    apiParams,
  }
}
