import { useEffect, useId, useRef } from 'react'
import type { TimelineEntryOut } from '@/api/generated'
import { announce } from '@/lib/announce'
import { cn } from '@/lib/utils'
import { dateTimeInZone, dayKeyInZone, timeInZone } from './case-dates'
import { CRISIS_TIMELINE_LINE, detailCopy } from './labels'
import { timelineEntryText } from './timeline-text'

type CaseTimelineProps = {
  /** The case's events, oldest first, as the API gives them. */
  entries: TimelineEntryOut[]
  /** The case's screening label. `crisis` adds a line after "Sent by": a fact, not a stored event. */
  screening: string | null
  /** The person's full name, for "Sent by Priya Raman" and "read Priya's words". */
  personName: string
  /** The viewer's location's time zone. */
  timeZone: string
  className?: string
}

/** The entries that are news to HR when they appear after the page was shown. */
const ANNOUNCED_KINDS = new Set(['text_read', 'status_changed'])

type Line = { key: string; text: string; occurredAt: string }

/** What an entry is, for telling a new one from one already shown. The one place it is built. */
function entryKey(e: TimelineEntryOut): string {
  return `${e.kind}|${e.occurredAt}|${e.actorPersonId ?? ''}`
}

/** Each entry with its key and which of its twins it is: two identical events are not one. */
function withOccurrence(entries: TimelineEntryOut[]) {
  const counts = new Map<string, number>()
  return entries.map((entry) => {
    const key = entryKey(entry)
    const nth = counts.get(key) ?? 0
    counts.set(key, nth + 1)
    return { entry, key, nth }
  })
}

function linesOf(entries: TimelineEntryOut[], screening: string | null, personName: string) {
  const lines: Line[] = []
  for (const { entry, key, nth } of withOccurrence(entries)) {
    const text = timelineEntryText(entry, { personName })
    if (text === null) continue
    lines.push({
      key: `${key}|${nth}`,
      text,
      occurredAt: entry.occurredAt,
    })
    if (entry.kind === 'opened' && screening === 'crisis') {
      lines.push({ key: 'crisis', text: CRISIS_TIMELINE_LINE, occurredAt: entry.occurredAt })
    }
  }
  return lines
}

/**
 * Every event on a case, oldest first (CaseTimeline.jsx): sent, the summary, each read of the
 * summary and of the words, each status change, and the safety check's crisis routing. The first
 * entry shows its date and time; a later one shows the date only when the day changes, otherwise
 * the time alone. An entry added after the page was shown is announced once, politely: "Added to
 * the timeline: ...". Nothing is announced on mount, and a refetch of the same entries adds nothing.
 */
function CaseTimeline({ entries, screening, personName, timeZone, className }: CaseTimelineProps) {
  const headingId = useId()
  const lines = linesOf(entries, screening, personName)
  // How many of each entry were already shown. One more of the same is new.
  const seen = useRef<Map<string, number> | null>(null)
  useEffect(() => {
    const placed = withOccurrence(entries)
    if (seen.current !== null) {
      const before = seen.current
      const added = placed
        .filter(({ key, nth }) => nth >= (before.get(key) ?? 0))
        // Only what HR just did: opening the words and changing the status. The summary is read
        // once per view and adds its row on every open, so announcing it would repeat.
        .filter(({ entry }) => ANNOUNCED_KINDS.has(entry.kind))
        .map(({ entry }) => timelineEntryText(entry, { personName }))
        .filter((text): text is string => text !== null)
      if (added.length > 0) announce(`Added to the timeline: ${added.join('; ')}`)
    }
    seen.current = new Map(placed.map(({ key, nth }) => [key, nth + 1]))
  }, [entries, personName])
  return (
    <section
      data-slot="case-timeline"
      aria-labelledby={headingId}
      className={cn(
        'rounded-lg border border-border bg-surface-sunken px-6 pt-4.5 pb-2 max-sm:px-4',
        className,
      )}
    >
      <h2 id={headingId} className="m-0 mb-3.5 text-body font-semibold">
        {detailCopy.timeline}
      </h2>
      {/* Explicit role: list-none drops list semantics in Safari and VoiceOver. */}
      {/* oxlint-disable-next-line jsx-a11y/no-redundant-roles */}
      <ol role="list" className="m-0 list-none p-0 pl-5.5">
        {lines.map((line, i) => {
          const previous = lines[i - 1]
          const newDay =
            !previous ||
            dayKeyInZone(previous.occurredAt, timeZone) !== dayKeyInZone(line.occurredAt, timeZone)
          const latest = i === lines.length - 1
          return (
            <li
              key={line.key}
              data-latest={latest || undefined}
              className={cn(
                'relative flex flex-col gap-px pb-4',
                // The dot, and the line down to the next entry.
                'before:absolute before:top-1.5 before:-left-4.5 before:box-border before:size-2 before:rounded-full before:border-2 before:border-border-strong before:bg-surface-raised before:content-[""]',
                'not-last:after:absolute not-last:after:top-4.5 not-last:after:bottom-0.5 not-last:after:-left-3.75 not-last:after:w-0.5 not-last:after:rounded-[1px] not-last:after:bg-border not-last:after:content-[""]',
                latest && 'before:border-primary',
              )}
            >
              <span className="text-ui font-regular text-pretty text-ink">{line.text}</span>
              <span className="text-small text-ink-muted tabular-nums">
                {newDay
                  ? dateTimeInZone(line.occurredAt, timeZone)
                  : timeInZone(line.occurredAt, timeZone)}
              </span>
            </li>
          )
        })}
      </ol>
    </section>
  )
}

export { CaseTimeline }
export type { CaseTimelineProps }
