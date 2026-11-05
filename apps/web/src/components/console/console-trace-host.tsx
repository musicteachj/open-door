import { useCallback, useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react'
import type { ConsoleTurnOut } from '@/api/generated'
import { BottomSheet, SheetTitle } from '@/components/ui/bottom-sheet'
import { useMediaQuery } from '@/hooks/use-media-query'
import { cn } from '@/lib/utils'
import { isTimed } from './labels'
import { TracePanel } from './trace-panel'
import { TurnTable } from './turn-table'

/** The design's phone breakpoint: at or below it the trace is a full-screen sheet. */
export const PHONE_QUERY = '(max-width: 640px)'

type ConsoleTraceHostProps = {
  turns: ConsoleTurnOut[]
  timeZone: string
  sectionTitle: (sectionId: string) => string | undefined
  loading?: boolean
  onAskQuestion?: () => void
  onTakeTour?: () => void
  tourDisabled?: boolean
  /** Shown above the table in the same column, so the tiles reflow beside a docked trace. */
  before?: ReactNode
  /** Shown below the table in the same column, such as the scoreboard. */
  after?: ReactNode
  /**
   * The page's own layout: `header` sits above everything in the content column (`columnClassName`
   * pads it), and the docked trace is flush against the sheet's right edge, as tall as the window,
   * outside that padding. Without `header` the host lays itself out for a gallery frame.
   */
  header?: ReactNode
  columnClassName?: string
}

/**
 * Owns which turn is open. It docks `TracePanel` beside the table (and what is passed as `before`
 * and `after`) on a wide window, and puts it in a full-screen sheet at 640 px and below. Opening a
 * row moves focus to the panel's heading, another row swaps the content, and Escape or the X
 * closes it and puts focus back on that row's button. It fetches nothing: the rows are given.
 */
function ConsoleTraceHost({
  turns,
  timeZone,
  sectionTitle,
  loading,
  onAskQuestion,
  onTakeTour,
  tourDisabled,
  before,
  after,
  header,
  columnClassName,
}: ConsoleTraceHostProps) {
  const [openId, setOpenId] = useState<string | null>(null)
  const traceId = useId()
  const phone = useMediaQuery(PHONE_QUERY)
  const rootRef = useRef<HTMLDivElement>(null)
  const returnTo = useRef<string | null>(null)
  // The open id as of the last effect, to tell a reload that dropped the row from a plain close.
  const lastOpenId = useRef<string | null>(null)
  // Whether focus is in the panel. Removing a focused element fires no focus event, so this is
  // still true when the panel has gone.
  const focusInPanel = useRef(false)

  // A row that is no longer in the list (it was reloaded away) closes the panel for good, so it
  // doesn't reopen on its own if the same id comes back. While the rows load they may come back,
  // so the panel only waits. Adjusting state while rendering is
  // React's way to reset state when a prop changes.
  const found = useMemo(() => turns.find((t) => t.id === openId && isTimed(t)), [turns, openId])
  if (openId !== null && found === undefined && !loading) setOpenId(null)
  // While the rows load there is nothing to trace, so the panel waits.
  const turn = loading ? undefined : found
  const selectedId = turn?.id ?? null

  const close = useCallback(() => {
    returnTo.current = selectedId
    setOpenId(null)
  }, [selectedId])
  // The same row again closes the panel, like a disclosure; another row swaps it.
  const open = useCallback(
    (id: string) => {
      if (!turns.some((t) => t.id === id && isTimed(t))) return
      if (id === selectedId) close()
      else setOpenId(id)
    },
    [turns, selectedId, close],
  )

  useEffect(() => {
    const onFocusIn = (event: FocusEvent) => {
      focusInPanel.current =
        event.target instanceof Element && !!event.target.closest('[data-slot="trace-panel"]')
    }
    document.addEventListener('focusin', onFocusIn)
    return () => document.removeEventListener('focusin', onFocusIn)
  }, [])

  // After the panel is gone, focus goes back to the row that opened it.
  useEffect(() => {
    const wasOpen = lastOpenId.current !== null
    lastOpenId.current = openId
    if (selectedId !== null) return
    const root = rootRef.current
    if (returnTo.current !== null) {
      const id = returnTo.current
      returnTo.current = null
      root?.querySelector<HTMLElement>(`[data-turn-id="${CSS.escape(id)}"]`)?.focus()
      return
    }
    // The open row was reloaded away while focus was in the panel: the first remaining row, else
    // the day's heading, else the first button (the empty state's), rather than the page body.
    if (openId !== null || !wasOpen || !focusInPanel.current) return
    focusInPanel.current = false
    const target =
      root?.querySelector<HTMLElement>('[data-turn-id]') ??
      root?.querySelector<HTMLElement>('[data-slot="day-heading"]') ??
      root?.querySelector<HTMLElement>('button')
    target?.focus()
  }, [selectedId, openId])

  const docked = turn !== undefined && !phone
  const panel = (inSheet: boolean) =>
    turn && (
      <TracePanel
        id={traceId}
        turn={turn}
        timeZone={timeZone}
        sectionTitle={sectionTitle}
        onClose={close}
        landmark={!inSheet}
        titleAs={inSheet ? SheetTitle : undefined}
        closeOnEscape={!inSheet}
        className={inSheet ? 'w-full border-l-0' : undefined}
      />
    )

  const page = header !== undefined
  const content = (
    <div className="flex min-w-0 flex-1 flex-col gap-10">
      {before}
      <TurnTable
        turns={turns}
        timeZone={timeZone}
        selectedId={selectedId}
        onOpen={open}
        traceId={traceId}
        panelOpen={docked}
        loading={loading}
        onAskQuestion={onAskQuestion}
        onTakeTour={onTakeTour}
        tourDisabled={tourDisabled}
      />
      {after}
    </div>
  )

  return (
    <div
      ref={rootRef}
      data-slot="console-trace-host"
      className={cn('flex items-start', !page && 'gap-6')}
    >
      {page ? (
        <div className={cn('min-w-0 flex-1', columnClassName)}>
          <div className="w-full max-w-270">
            {header}
            <div className="mt-10">{content}</div>
          </div>
        </div>
      ) : (
        content
      )}
      {docked && (
        <div
          data-slot="trace-dock"
          className={cn(
            'sticky top-3 h-[calc(100dvh-24px)] flex-none self-start',
            // Beside the sheet's content, not inside it: the panel's own border-l is the edge.
            page && 'w-panel',
          )}
        >
          {panel(false)}
        </div>
      )}
      {turn && phone && (
        <BottomSheet full onClose={close}>
          {panel(true)}
        </BottomSheet>
      )}
    </div>
  )
}

export { ConsoleTraceHost }
export type { ConsoleTraceHostProps }
