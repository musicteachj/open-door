import { CalendarMinus, Check, CircleAlert } from 'lucide-react'
import { useId, type ReactNode } from 'react'
import type { DrawOut, LeaveTypeName, RuleRefOut, SkippedDay } from '@/api/generated'
import { cn } from '@/lib/utils'
import { addDays, longRange } from './dates'
import { foldedScheduleLine, leftLines, previewCopy, skippedLine } from './labels'
import { RuleChips } from './rule-chip'

type PreviewBlockProps = {
  type: LeaveTypeName
  /** The days that count, in order. */
  countedDays: string[]
  skippedDays: SkippedDay[]
  /** Counted days that another request already covers. */
  overlappingDays?: string[]
  /** The API's label for the whole request, or null when nothing counted. */
  amountLabel: string | null
  /** The balance before and after, per year for sick time. */
  draws: DrawOut[]
  rules: RuleRefOut[]
  /** A refusal applies: the total stays, but no "left after this". */
  refused?: boolean
  /** The current year, so a sick request in another year names its year. */
  thisYear?: number
  /** Nothing is picked yet. */
  empty?: boolean
  /** Muted ink, for a card that ended without a change. */
  muted?: boolean
  /** The figures are being worked out again: the live region is marked busy. */
  busy?: boolean
  className?: string
}

/** More than this many counted days fold into runs. */
const MAX_SINGLE_LINES = 5
/** More than this many skipped days off the schedule fold into one line. */
const MAX_OFF_SCHEDULE_LINES = 2

type Line =
  | { key: string; kind: 'counted' | 'blocked'; text: string }
  | { key: string; kind: 'skipped'; text: string }

function countedLines(counted: string[], blocked: Set<string>): Line[] {
  const collapse = counted.length > MAX_SINGLE_LINES
  const items = counted.map((day) => ({ day, blocked: blocked.has(day) }))
  // Runs are days that follow each other on the calendar and are alike (all open, or all booked).
  const groups: { days: string[]; blocked: boolean }[] = []
  for (const item of items) {
    const last = groups[groups.length - 1]
    const run = last && addDays(last.days[last.days.length - 1]!, 1) === item.day
    if (collapse && last && last.blocked === item.blocked && run) last.days.push(item.day)
    else groups.push({ days: [item.day], blocked: item.blocked })
  }
  return groups.map((group) => ({
    key: `${group.blocked ? 'blocked' : 'counted'}-${group.days[0]}`,
    kind: group.blocked ? 'blocked' : 'counted',
    text: longRange(group.days[0]!, group.days[group.days.length - 1]!),
  }))
}

function skippedLines(skipped: SkippedDay[]): Line[] {
  const offSchedule = (item: SkippedDay) => item.reason === 'not scheduled'
  // Past two days off the schedule they fold into one line naming the weekdays. Holidays never do.
  const folded = skipped.filter(offSchedule)
  const fold = folded.length > MAX_OFF_SCHEDULE_LINES
  const lines: Line[] = []
  let placed = false
  for (const item of skipped) {
    if (fold && offSchedule(item)) {
      if (!placed) {
        const text = foldedScheduleLine(folded.map((entry) => entry.day))
        lines.push({ key: 'off-schedule', kind: 'skipped', text })
      }
      placed = true
    } else {
      lines.push({ key: `skipped-${item.day}`, kind: 'skipped', text: skippedLine(item) })
    }
  }
  return lines
}

/**
 * "What this uses" (PreviewBlock.jsx): the counted days (dates only; past five days they fold into
 * runs), the days skipped and why, a day already booked, then the total and what is left, and the
 * source chips. It takes the fields the check route and a request card share. Every figure is an
 * API label. A polite live region, with hidden "Counted:", "Skipped:", and "Can't be counted:"
 * before each line.
 */
function PreviewBlock({
  type,
  countedDays,
  skippedDays,
  overlappingDays = [],
  amountLabel,
  draws,
  rules,
  refused = false,
  thisYear,
  empty = false,
  muted = false,
  busy = false,
  className,
}: PreviewBlockProps) {
  const titleId = useId()
  // One live region stays mounted from the empty line to the first preview, so a screen reader
  // that is already watching it hears the first lines arrive.
  const live = (children: ReactNode) => (
    <div data-slot="preview-live" aria-live="polite" aria-busy={busy || undefined}>
      {children}
    </div>
  )
  if (empty) {
    return live(
      <p
        data-slot="preview-block"
        data-state="empty"
        className={cn(
          'm-0 rounded-lg border border-border-subtle bg-surface-sunken px-4 py-3.5 text-ui text-ink-muted',
          className,
        )}
      >
        {previewCopy.empty}
      </p>,
    )
  }
  const blocked = new Set(overlappingDays)
  const lines = [...countedLines(countedDays, blocked), ...skippedLines(skippedDays)]
  const nothingCounted = countedDays.length === 0
  const anyBooked = blocked.size > 0
  const showTotal = !nothingCounted && !anyBooked && amountLabel !== null
  const lefts = showTotal && !refused ? leftLines(type, draws, thisYear) : []
  // One line follows the total; several (sick time across New Year) each get their own.
  const inlineLeft = lefts.length === 1 ? lefts[0] : undefined
  const separateLefts = lefts.length > 1 ? lefts : []
  return live(
    <section
      data-slot="preview-block"
      aria-labelledby={titleId}
      className={cn(
        'overflow-hidden rounded-lg border border-border',
        muted ? 'text-ink-muted' : 'text-ink',
        className,
      )}
    >
      <h3
        id={titleId}
        className="m-0 border-b border-border-subtle bg-surface-sunken px-4 py-2.5 text-small font-semibold"
      >
        {previewCopy.title}
      </h3>
      <div className="px-4 pt-1.5 pb-3">
        {lines.length > 0 && (
          <ul className="m-0 list-none p-0">
            {lines.map((line) => (
              <li
                key={line.key}
                className={cn(
                  'grid items-start gap-2.5 py-1.5 text-ui tabular-nums',
                  line.kind === 'skipped'
                    ? 'grid-cols-[16px_minmax(0,1fr)] text-pretty text-ink-muted'
                    : 'grid-cols-[16px_minmax(0,1fr)_auto]',
                )}
              >
                {line.kind === 'counted' && (
                  <Check
                    aria-hidden="true"
                    strokeWidth={2}
                    className={cn('mt-0.5 size-4', muted ? 'text-ink-muted' : 'text-primary')}
                  />
                )}
                {line.kind === 'blocked' && (
                  <CircleAlert
                    aria-hidden="true"
                    strokeWidth={1.75}
                    className="mt-0.5 size-4 text-danger"
                  />
                )}
                {line.kind === 'skipped' && (
                  <CalendarMinus aria-hidden="true" className="mt-0.5 size-4 text-ink-muted" />
                )}
                <span>
                  <span className="sr-only">
                    {line.kind === 'counted'
                      ? `${previewCopy.counted} `
                      : line.kind === 'blocked'
                        ? `${previewCopy.blocked} `
                        : `${previewCopy.skipped} `}
                  </span>
                  {line.text}
                </span>
                {line.kind === 'blocked' && <span>{previewCopy.alreadyBooked}</span>}
              </li>
            ))}
          </ul>
        )}
        {nothingCounted && (
          <p className="m-0 mt-1.5 border-t border-border-subtle pt-3 text-ui text-ink-muted">
            {previewCopy.nothingCounted}
          </p>
        )}
        {showTotal && (
          <div className="mt-1.5 border-t border-border-subtle pt-3 text-body tabular-nums">
            <p className="m-0 text-pretty">
              <strong className="font-semibold">{amountLabel}</strong>
              {inlineLeft && <span className="text-ink-muted"> · {inlineLeft}</span>}
            </p>
            {separateLefts.map((text) => (
              <p key={text} className="m-0 text-ui text-ink-muted">
                {text}
              </p>
            ))}
          </div>
        )}
        <RuleChips rules={rules} className="mt-3" />
      </div>
    </section>,
  )
}

export { PreviewBlock }
export type { PreviewBlockProps }
