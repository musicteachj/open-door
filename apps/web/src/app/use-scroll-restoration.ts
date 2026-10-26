import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useLocation, useNavigationType } from 'react-router'

// How long Back keeps trying to reach the saved position while the page is still too short.
const SETTLE_MS = 2000
// The positions survive a reload in sessionStorage (this tab only), as React Router's own did.
const STORAGE_KEY = 'od.scrollPositions'
const MAX_ENTRIES = 50

function load(): Map<string, number> {
  try {
    const parsed: unknown = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? '[]')
    if (!Array.isArray(parsed)) return new Map()
    return new Map(
      parsed.filter(
        (entry): entry is [string, number] =>
          Array.isArray(entry) && typeof entry[0] === 'string' && typeof entry[1] === 'number',
      ),
    )
  } catch {
    return new Map()
  }
}

function persist(positions: Map<string, number>) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...positions].slice(-MAX_ENTRIES)))
  } catch {
    // Storage full or blocked: positions then last only as long as the page.
  }
}

/** Records a position as the newest, so the oldest are the ones dropped past the cap. */
function remember(positions: Map<string, number>, key: string, top: number) {
  positions.delete(key)
  positions.set(key, top)
  while (positions.size > MAX_ENTRIES) positions.delete(positions.keys().next().value!)
}

/**
 * What a navigation puts in its history state to say "this only opens or closes a panel on the
 * page, so leave the scroll alone". Pass it with `preventScrollReset`, which keeps React Router's
 * own handling out of the way.
 */
export const KEEP_SCROLL_STATE = { keepScroll: true } as const

/** True for a history entry that was marked with `keepScroll`. */
function isMarked(state: unknown): boolean {
  return (
    typeof state === 'object' &&
    state !== null &&
    (state as { keepScroll?: unknown }).keepScroll === true
  )
}

/**
 * Scroll for a router with no loaders, on the window (the shell's sheet grows with its content, so
 * the page is what scrolls). React Router's <ScrollRestoration> jumps to the top on every location
 * change, including a search's replace, and gave up on Back to the directory, so this takes its
 * place.
 *
 * - A new page (a push) starts at the top.
 * - A push to a history entry marked `keepScroll` (see `KEEP_SCROLL_STATE`), on the same page,
 *   keeps the position, and so do Back and Forward between two entries of the same page when
 *   either is marked: opening a panel must not throw the reader to the top of the thread, and
 *   closing it must not jump back to where the page was when it opened. The marker, not the URL,
 *   says so, so any panel can use it.
 * - A replace on the same page keeps the position: typing a search must not throw the visitor up.
 *   A replace to another page starts at the top.
 * - Back and Forward (a pop) return to where that history entry was left, saved by `location.key`.
 *   If the page is not yet tall enough (the rows are still arriving), it keeps trying for a moment.
 */
export function useScrollRestoration() {
  const location = useLocation()
  const type = useNavigationType()
  const [positions] = useState(load)
  const current = useRef({
    key: location.key,
    pathname: location.pathname,
    keep: isMarked(location.state),
  })
  // True while a restore is still trying to reach its position. The page is too short then, so
  // what the browser reports is a cut-short position that must not replace the saved one.
  const restoring = useRef(false)

  useEffect(() => {
    const previous = window.history.scrollRestoration
    window.history.scrollRestoration = 'manual'
    const save = () => {
      if (!restoring.current) remember(positions, current.current.key, window.scrollY)
    }
    const flush = () => persist(positions)
    window.addEventListener('scroll', save, { passive: true })
    window.addEventListener('pagehide', flush)
    return () => {
      window.removeEventListener('scroll', save)
      window.removeEventListener('pagehide', flush)
      window.history.scrollRestoration = previous
      flush()
    }
  }, [positions])

  useLayoutEffect(() => {
    const previous = current.current
    const marked = isMarked(location.state)
    current.current = { key: location.key, pathname: location.pathname, keep: marked }
    if (previous.key === location.key) {
      // The first render. After a reload the browser's own restoration is off, so this puts the
      // page back where this history entry was left. A visit with no saved position stays at the
      // top. "default" is the key of every first visit, so a position under it isn't this page's.
      const saved = positions.get(location.key)
      if (type === 'POP' && location.key !== 'default' && saved !== undefined)
        return restore(saved, restoring)
      return
    }

    // A move on the same page that opens or closes a panel never moves it. A push counts when
    // its own entry is marked; Back and Forward when either entry is (closing goes back to the
    // unmarked page, reopening forward to the marked one).
    const samePage = previous.pathname === location.pathname
    const keep = samePage && (type === 'POP' ? previous.keep || marked : type === 'PUSH' && marked)
    let stop = () => {}
    if (keep) {
      // Nothing to do: the reader stays where they are, and this entry is noted below.
    } else if (type === 'POP') {
      stop = restore(positions.get(location.key) ?? 0, restoring)
    } else if (type === 'PUSH' || !samePage) {
      window.scrollTo(0, 0)
    }
    // This entry's position starts as wherever the page is now, so leaving it unscrolled and
    // coming back still lands in the right place.
    // On a restore still under way the saved position stands: the page isn't tall enough yet.
    if (!restoring.current) {
      remember(positions, location.key, window.scrollY)
      persist(positions)
    }
    return stop
  }, [location.key, location.pathname, location.state, type, positions])
}

// What a visitor does to take over the scroll themselves.
const TAKEOVER = ['wheel', 'touchstart', 'keydown', 'pointerdown'] as const

/**
 * Scrolls to `top`, and keeps trying while the page grows into it. `active` is true until it gets
 * there, times out, is stopped, or the visitor scrolls for themselves. Returns how to stop.
 */
function restore(top: number, active: { current: boolean }) {
  window.scrollTo(0, top)
  if (window.scrollY >= top - 1) return () => {}
  active.current = true
  const observer = new ResizeObserver(() => {
    window.scrollTo(0, top)
    if (window.scrollY >= top - 1) finish()
  })
  const timer = setTimeout(() => finish(), SETTLE_MS)
  function finish() {
    clearTimeout(timer)
    observer.disconnect()
    for (const type of TAKEOVER) window.removeEventListener(type, finish)
    active.current = false
  }
  for (const type of TAKEOVER) window.addEventListener(type, finish, { passive: true })
  observer.observe(document.body)
  return finish
}
