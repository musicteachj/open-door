// The rows are CSS grids, so the table is built from ARIA roles on divs: a real <tr> with
// display: grid loses its table semantics in some browsers.
/* oxlint-disable jsx-a11y/prefer-tag-over-role */
import { useId, useMemo, useState, type ReactNode } from 'react'
import type { ConsoleTurnOut } from '@/api/generated'
import { EmptyCell } from '@/components/core/empty-cell'
import { LoadingStatus } from '@/components/feedback/loading-status'
import { outcomeBadgeFor } from '@/components/status/outcome-badges'
import { StatusBadge } from '@/components/timeoff/status-badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import {
  dayHeading,
  formatDuration,
  formatTurnCost,
  isTimed,
  roleLabel,
  turnName,
  zoneAbbreviation,
} from './labels'
import { RedactedRow } from './redacted-row'
import { SafetyLabel } from './safety-label'

type TurnTableProps = {
  /** The API's rows, in its order: each day's timed rows newest first, then its flagged rows. */
  turns: ConsoleTurnOut[]
  /** The viewer's location's zone, for the times. */
  timeZone: string
  selectedId?: string | null
  onOpen?: (id: string) => void
  /** The id of the trace panel the open row controls. Leave out when no panel is in the page. */
  traceId?: string
  /** A docked panel narrows the columns and stacks the injection tag. */
  panelOpen?: boolean
  loading?: boolean
  /** The empty state's two ways forward. */
  onAskQuestion?: () => void
  onTakeTour?: () => void
  /**
   * The tour cannot start right now (a persona switch is in flight): "Take the tour" is disabled.
   */
  tourDisabled?: boolean
}

// The design's columns (console.css, --od-turn-cols), plain and with a docked panel.
const COLUMNS =
  '[--od-turn-cols:96px_minmax(0,1.3fr)_minmax(0,1.4fr)_minmax(0,1.6fr)_56px_80px_72px_88px] data-[panel]:[--od-turn-cols:64px_minmax(0,0.9fr)_minmax(0,1.1fr)_minmax(0,1.4fr)_40px_56px_52px_52px]'
const GRID = 'grid grid-cols-[var(--od-turn-cols)] gap-x-3 px-3'
// At 640 px and below each row is a stacked card (the design's grid areas).
const PHONE_ROW =
  "max-[640px]:grid-cols-[minmax(0,1fr)_auto] max-[640px]:gap-y-1.5 max-[640px]:px-4 max-[640px]:py-3.5 max-[640px]:[grid-template-areas:'time_cost'_'who_ft'_'out_out'_'safe_safe'_'tools_cited']"
const AREA = {
  time: 'max-[640px]:[grid-area:time]',
  who: 'max-[640px]:[grid-area:who]',
  out: 'max-[640px]:[grid-area:out]',
  safe: 'max-[640px]:[grid-area:safe]',
  tools: 'max-[640px]:[grid-area:tools] max-[640px]:text-left',
  cited: 'max-[640px]:[grid-area:cited] max-[640px]:text-right',
  cost: 'max-[640px]:[grid-area:cost]',
  ft: 'max-[640px]:[grid-area:ft]',
}

/** The cell's name as an inline prefix, shown only in the phone's stacked card. */
function Prefix({ children }: { children: ReactNode }) {
  return <span className="hidden text-ink-muted max-[640px]:inline">{children} </span>
}

/**
 * The name of a cell that shows none, for a phone, where the column headers are hidden ("Cost
 * $0.021"). It is not displayed at desktop widths, so the headers are not read twice.
 */
function PhoneName({ children }: { children: ReactNode }) {
  return (
    <span data-phone-name="" className="hidden max-[640px]:sr-only max-[640px]:inline">
      {children}{' '}
    </span>
  )
}

function Header({ zone }: { zone: string }) {
  const right = 'text-right max-[640px]:text-left'
  return (
    <div role="rowgroup" className="max-[640px]:hidden">
      <div
        role="row"
        className={cn(GRID, 'items-end border-b border-border py-2 text-small text-ink-muted')}
      >
        {[
          [`Time (${zone})`, ''],
          ['Asked by', ''],
          ['Outcome', ''],
          ['Safety check', ''],
          ['Tools', right],
          ['Cited', ''],
          ['Cost', right],
          ['First token', right],
        ].map(([label, align]) => (
          <span key={label} role="columnheader" className={cn('font-normal', align)}>
            {label}
          </span>
        ))}
      </div>
    </div>
  )
}

function TurnRow({
  turn,
  timeZone,
  selected,
  traceId,
  stacked,
  onOpen,
}: {
  turn: ConsoleTurnOut
  timeZone: string
  selected: boolean
  traceId?: string
  stacked: boolean
  onOpen?: (id: string) => void
}) {
  const name = turnName(turn, timeZone)
  const badge = outcomeBadgeFor(turn.outcome)
  const cited = turn.sectionsCited ?? []
  return (
    // A click anywhere in the row opens it; the button in the Time cell is the keyboard's way in.
    // oxlint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions
    <div
      role="row"
      data-slot="turn-row"
      data-selected={selected || undefined}
      onClick={() => onOpen?.(turn.id)}
      className={cn(
        GRID,
        PHONE_ROW,
        'min-h-14 cursor-pointer items-start border-b border-border-subtle py-2.5 transition-colors hover:bg-primary-tint',
        'data-[selected]:bg-primary-tint data-[selected]:shadow-[inset_3px_0_0_var(--color-primary)]',
        // The keyboard ring goes around the whole row, not the small button.
        'has-[:focus-visible]:outline-2 has-[:focus-visible]:-outline-offset-2 has-[:focus-visible]:outline-focus-ring',
      )}
    >
      <span role="cell" className={AREA.time}>
        <PhoneName>Time</PhoneName>
        <button
          type="button"
          data-turn-id={turn.id}
          aria-expanded={selected}
          aria-controls={selected ? traceId : undefined}
          className="cursor-pointer border-0 bg-transparent p-0 font-semibold whitespace-nowrap text-ink outline-none"
        >
          {name.time}
          <span className="sr-only">{name.hidden}</span>
        </button>
      </span>
      <span role="cell" className={cn('flex min-w-0 flex-col', AREA.who)}>
        <PhoneName>Asked by</PhoneName>
        <span>{turn.askerRole === null ? <EmptyCell /> : roleLabel(turn.askerRole)}</span>
        <span className="text-small text-ink-muted">{turn.askerLocation}</span>
      </span>
      <span role="cell" className={cn('flex min-w-0 flex-col items-start gap-1', AREA.out)}>
        <PhoneName>Outcome</PhoneName>
        {badge === null ? <EmptyCell /> : <StatusBadge status={badge} />}
        {turn.cardAction !== null && (
          <span className="text-small text-ink-muted">Offered a card</span>
        )}
      </span>
      <span role="cell" className={AREA.safe}>
        <PhoneName>Safety check</PhoneName>
        <SafetyLabel
          category={turn.guardCategory}
          injection={turn.injectionSuspected}
          stacked={stacked}
        />
      </span>
      <span role="cell" className={cn('text-right leading-6', AREA.tools)}>
        <Prefix>Tools</Prefix>
        {turn.tools?.length ?? 0}
      </span>
      <span role="cell" className={cn('leading-6', AREA.cited)}>
        <Prefix>Cited</Prefix>
        {cited.length > 0 ? cited.join(', ') : <EmptyCell />}
      </span>
      <span role="cell" className={cn('text-right leading-6', AREA.cost)}>
        <PhoneName>Cost</PhoneName>
        {formatTurnCost(turn.costUsd)}
      </span>
      <span role="cell" className={cn('text-right leading-6 whitespace-nowrap', AREA.ft)}>
        <PhoneName>First token</PhoneName>
        {turn.firstTextMs === null ? <EmptyCell /> : formatDuration(turn.firstTextMs)}
      </span>
    </div>
  )
}

function SkeletonRows() {
  const widths = ['70%', '75%', '60%', '55%', '16px', '40%', '44px', '32px']
  return (
    <>
      {[0, 1, 2, 3, 4, 5].map((row) => (
        <div
          key={row}
          role="row"
          aria-hidden="true"
          data-slot="turn-skeleton-row"
          className={cn(
            GRID,
            // On a phone the eight columns collapse to two bars, so the row never outgrows it.
            'h-14 items-center border-b border-border-subtle max-[640px]:grid-cols-[minmax(0,1fr)_auto] max-[640px]:[&>:nth-child(n+3)]:hidden',
          )}
        >
          {widths.map((width, col) => (
            <Skeleton
              key={col}
              style={{ width }}
              className={col === 4 || col > 5 ? 'justify-self-end' : undefined}
            />
          ))}
        </div>
      ))}
    </>
  )
}

/** The rows grouped by their day, in the API's order. */
function byDay(turns: ConsoleTurnOut[]): [string, ConsoleTurnOut[]][] {
  const days = new Map<string, ConsoleTurnOut[]>()
  for (const turn of turns) {
    const day = days.get(turn.occurredOn)
    if (day === undefined) days.set(turn.occurredOn, [turn])
    else day.push(turn)
  }
  return [...days]
}

/**
 * The sandbox's turns as an ARIA table, a day at a time (TurnTable.jsx). It keeps the API's order
 * and offers no sorting, ranking, or scoring. It shows only what a row carries: never a name,
 * question, answer, or tool input. A timed row has one button in its Time cell; a redacted row is
 * plain text. Opening a row is the host's job (`ConsoleTraceHost`).
 */
function TurnTable({
  turns,
  timeZone,
  selectedId = null,
  onOpen,
  traceId,
  panelOpen = false,
  loading = false,
  onAskQuestion,
  onTakeTour,
  tourDisabled = false,
}: TurnTableProps) {
  const uid = useId()
  const days = useMemo(() => byDay(turns), [turns])
  // The zone's name depends on the date (MDT or MST), so each day takes it from its own timed
  // rows. The loading header and a day with no timed row use the present.
  const [now] = useState(() => new Date())
  const zoneFor = (rows: ConsoleTurnOut[]) =>
    zoneAbbreviation(timeZone, rows.find((t) => t.occurredAt !== null)?.occurredAt ?? now)

  if (!loading && turns.length === 0) {
    // Left-aligned under a subtle rule, as the design shows it (not the centered EmptyState).
    return (
      <div
        data-slot="turn-empty"
        className="flex flex-col items-start gap-4 border-t border-border-subtle pt-8"
      >
        <p className="m-0 text-body text-ink">
          No questions yet in this sandbox. Ask something, or take the tour.
        </p>
        <div className="flex flex-wrap gap-3">
          <Button variant="primary" onClick={() => onAskQuestion?.()}>
            Ask a question
          </Button>
          <Button variant="secondary" disabled={tourDisabled} onClick={() => onTakeTour?.()}>
            Take the tour
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div
      data-slot="turn-table"
      data-panel={panelOpen || undefined}
      className={cn('flex flex-col gap-8 text-ui font-normal text-ink tabular-nums', COLUMNS)}
    >
      <LoadingStatus loading={loading} text="Loading the sandbox figures" />
      {loading ? (
        <div role="table" aria-label="Turns" aria-busy="true">
          <Header zone={zoneFor([])} />
          <div role="rowgroup">
            <SkeletonRows />
          </div>
        </div>
      ) : (
        days.map(([day, rows]) => {
          const headingId = `${uid}-day-${day}`
          return (
            // The table carries the heading as its name, so this wrapper doesn't repeat it.
            <div key={day}>
              <h3
                id={headingId}
                // The host puts focus here when the open row disappears and none is left.
                tabIndex={-1}
                data-slot="day-heading"
                className="m-0 mb-3 text-body leading-[22px] font-semibold outline-none"
              >
                {dayHeading(day, rows.length)}
              </h3>
              <div role="table" aria-labelledby={headingId}>
                <Header zone={zoneFor(rows)} />
                <div role="rowgroup">
                  {rows.map((turn) =>
                    isTimed(turn) ? (
                      <TurnRow
                        key={turn.id}
                        turn={turn}
                        timeZone={timeZone}
                        selected={turn.id === selectedId}
                        traceId={traceId}
                        stacked={panelOpen}
                        onOpen={onOpen}
                      />
                    ) : (
                      // Flagged, or without a time to show: nothing to open.
                      <RedactedRow key={turn.id} turn={turn} />
                    ),
                  )}
                </div>
              </div>
            </div>
          )
        })
      )}
    </div>
  )
}

export { TurnTable }
export type { TurnTableProps }
