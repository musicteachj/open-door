import { useCallback, useEffect, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { KEEP_SCROLL_STATE } from '@/app/use-scroll-restoration'
import { parseSourceKey } from './source-key'

/** The one search parameter: the open passage, as a source key ("CA-4.3~p2"). */
export const SOURCE_PARAM = 'source'

/**
 * Set on the history entry that opening the panel added, so closing can go back over it, with the
 * scroll marker every panel navigation carries (the scroll hook keeps the position for it).
 */
type SourceState = { openedSource?: true; keepScroll?: true } | null

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
  const value = parseSourceKey(raw) === null ? null : raw
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

  /** Drops `?source=` by replacing the entry: the passage belongs to a conversation that went away. */
  const clear = useCallback(() => {
    if (value === null) return
    void navigate(withSource(null), { replace: true, preventScrollReset: true })
  }, [navigate, value, withSource])

  return { key: value, open, close, clear }
}
