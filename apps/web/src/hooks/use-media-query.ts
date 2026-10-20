import { useCallback, useMemo, useSyncExternalStore } from 'react'

/**
 * Whether a CSS media query matches now, and again when that changes. Where there is no
 * `matchMedia` (jsdom, a server) nothing matches, so a page that asks for a narrow window shows
 * its wide layout there.
 */
export function useMediaQuery(query: string): boolean {
  // One MediaQueryList per query, kept for as long as the query is the same: the browser is asked
  // once, not on every render, and the listener and the reading share the same list.
  const list = useMemo(
    () => (typeof window.matchMedia === 'function' ? window.matchMedia(query) : null),
    [query],
  )
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (list === null) return () => {}
      list.addEventListener('change', onChange)
      return () => list.removeEventListener('change', onChange)
    },
    [list],
  )
  return useSyncExternalStore(
    subscribe,
    () => list?.matches ?? false,
    () => false,
  )
}
