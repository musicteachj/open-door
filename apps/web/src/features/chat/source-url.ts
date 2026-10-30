import { useCallback, useEffect, useMemo, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { KEEP_SCROLL_STATE } from '@/app/use-scroll-restoration'
import { registerReset } from '@/lib/identity'
import { parseSourceKey } from './source-key'

/** The one search parameter: the open passage, as a source key ("CA-4.3~p2"). */
export const SOURCE_PARAM = 'source'

/**
 * Set on the history entry that opening the panel added, so closing can go back over it, with the
 * scroll marker every panel navigation carries (the scroll hook keeps the position for it).
 */
type SourceState = { openedSource?: true; keepScroll?: true } | null

// The entries already being gone back over. A pushed entry's key is unique, so this never blocks a
// later panel. Only the last 50 are kept (as in the session list below), and a persona switch
// empties it.
const MAX_REMEMBERED = 50
const goneBackOver = new Set<string>()
registerReset(() => goneBackOver.clear())

function rememberGoneBackOver(key: string) {
  goneBackOver.add(key)
  if (goneBackOver.size > MAX_REMEMBERED) {
    const oldest = goneBackOver.values().next().value
    if (oldest !== undefined) goneBackOver.delete(oldest)
  }
}

/** How many entries are remembered as gone back over. For tests. */
export function goneBackOverCount(): number {
  return goneBackOver.size
}

const STALE_KEY = 'od.staleSourceEntries'

/**
 * The keys of history entries that opened a panel and were then gone back over ("Start a new
 * conversation" closes the panel that way). Going Forward to one would open a passage on a
 * conversation it does not belong to, so such an entry reads as closed. Kept in the session, so a
 * reload does not forget them.
 */
function staleEntries(): string[] {
  try {
    const parsed: unknown = JSON.parse(sessionStorage.getItem(STALE_KEY) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter((key) => typeof key === 'string') : []
  } catch {
    return []
  }
}

function markStale(key: string) {
  try {
    sessionStorage.setItem(STALE_KEY, JSON.stringify([...staleEntries(), key].slice(-50)))
  } catch {
    // Storage is blocked: the entry is simply not remembered after a reload.
  }
}

/**
 * The open source panel, kept in the URL (`?source=`) so Back closes it and the address can be
 * shared. `key` is null when the URL names no usable passage.
 *
 * History: opening adds an entry (Back closes the panel), and showing another passage replaces it
 * (one Back still closes it, however many were looked at). Closing goes back over the entry the
 * panel added. A panel that came with the URL (a reload, a shared link) has no entry of its own,
 * so closing replaces the address instead of leaving a step that does nothing.
 */
export function useSourceUrl() {
  const location = useLocation()
  const navigate = useNavigate()
  const raw = new URLSearchParams(location.search).get(SOURCE_PARAM)
  // Read from storage once per entry, not on every render.
  const stale = useMemo(
    () => raw !== null && staleEntries().includes(location.key),
    // The key names the entry. `raw` is part of what the entry says, so it is a dependency too.
    [location.key, raw],
  )
  const value = parseSourceKey(raw) === null || stale ? null : raw
  const state = location.state as SourceState

  // Between a close and the page catching up a second close must not go back twice (Escape both
  // pressed in the panel and heard by the page, say). It is re-armed when the source changes.
  const closing = useRef(false)
  useEffect(() => {
    closing.current = false
  }, [value])

  const withSource = useCallback(
    (next: string | null) => {
      const params = new URLSearchParams(location.search)
      if (next === null) params.delete(SOURCE_PARAM)
      else params.set(SOURCE_PARAM, next)
      const search = params.toString()
      return { pathname: location.pathname, search: search === '' ? '' : `?${search}` }
    },
    [location.pathname, location.search],
  )

  const close = useCallback(() => {
    if (value === null || closing.current) return
    closing.current = true
    if (state?.openedSource === true) void navigate(-1)
    else {
      // A replace on the same page never moves the scroll, so it carries no marker: the entry it
      // leaves behind is the page itself.
      void navigate(withSource(null), { replace: true, preventScrollReset: true })
    }
  }, [navigate, state, value, withSource])

  const open = useCallback(
    (next: string) => {
      if (next === value) return close()
      const to = withSource(next)
      if (value === null) {
        void navigate(to, {
          state: { ...KEEP_SCROLL_STATE, openedSource: true },
          preventScrollReset: true,
        })
      } else {
        // Keeps what the entry says about who opened it.
        void navigate(to, {
          replace: true,
          state,
          preventScrollReset: true,
        })
      }
    },
    [close, navigate, state, value, withSource],
  )

  /**
   * Drops the panel: its passage belongs to a conversation that went away. A panel the person
   * opened has its own history entry, and that entry is gone back over (replacing it would leave
   * a Back step that changes nothing); the entry stays ahead of us, so it is marked stale and
   * reads as closed if the person goes Forward to it. A panel that came with the URL has no entry
   * of its own, so the address is replaced.
   */
  const clear = useCallback(() => {
    if (value === null) return
    if (state?.openedSource === true) {
      // Once per entry, whoever asks (a development double effect, or two consumers of this hook):
      // a second Back would leave the page.
      if (goneBackOver.has(location.key)) return
      rememberGoneBackOver(location.key)
      markStale(location.key)
      void navigate(-1)
    } else {
      void navigate(withSource(null), { replace: true, preventScrollReset: true })
    }
  }, [location.key, navigate, state, value, withSource])

  // Arriving on a stale entry (Forward): drop its `?source=` from the address.
  useEffect(() => {
    if (stale) void navigate(withSource(null), { replace: true, preventScrollReset: true })
  }, [navigate, stale, withSource])

  return { key: value, open, close, clear }
}
