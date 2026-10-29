import { ChevronRight, Shield } from 'lucide-react'
import { Link } from 'react-router'
import type { QueueItemOut } from '@/api/generated'
import { SegmentedControl } from '@/components/timeoff/segmented-control'
import { StatusBadge } from '@/components/timeoff/status-badge'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { initialsOf } from '@/lib/initials'
import { CASE_BADGE_WORDS } from '@/components/status/case-badges'
import { cn } from '@/lib/utils'
import { dayInZone } from './case-dates'
import {
  categoryLabel,
  CRISIS_FACT,
  hrBadge,
  QUEUE_EMPTY,
  QUEUE_FILTERS,
  replyLine,
  type QueueFilterValue,
} from './labels'

type CaseQueueTableProps = {
  /** The page of cases, in the order the server gave. The table never reorders them. */
  rows: QueueItemOut[]
  filter: QueueFilterValue
  onFilterChange: (filter: QueueFilterValue) => void
  /** Today's calendar date in the viewer's location ("2026-10-26"), to say when a reply is due. */
  today: string
  /** The viewer's location's time zone, for sent and status days. */
  timeZone: string
  className?: string
}

// CaseQueueTable.jsx and hrcases.css (.od-cq): six columns, 24 px apart, a 64 px row. Under 640 px
// the header hides and a row stacks: the person, the category, then the reply line and the badge.
const COLUMNS =
  'grid grid-cols-[minmax(0,2.5fr)_minmax(0,2fr)_minmax(0,1fr)_minmax(0,1.6fr)_120px_16px] items-center gap-x-6 px-3 max-sm:grid-cols-[minmax(0,1fr)_auto]'

function rowName(c: QueueItemOut, today: string, timeZone: string): string {
  const person = `${c.givenName} ${c.familyName}, ${c.title}, ${c.locationName}`
  const category = c.crisis
    ? `${categoryLabel(c.category)}. ${CRISIS_FACT.slice(0, -1)}`
    : categoryLabel(c.category)
  return (
    [
      person,
      category,
      `Sent ${dayInZone(c.sentAt, timeZone)}`,
      replyLine(c, today, timeZone),
      CASE_BADGE_WORDS[hrBadge(c.status)],
    ].join('. ') + '.'
  )
}

/**
 * HR's case queue: a filter and one link per case. Facts only: the person, the category, when it
 * was sent, the reply line, and the status. Never any part of a case's words or summary, which this
 * component is never given. An overdue reply and the crisis fact are neutral ink: they state a
 * fact and never rank or warn.
 */
function CaseQueueTable({
  rows,
  filter,
  onFilterChange,
  today,
  timeZone,
  className,
}: CaseQueueTableProps) {
  return (
    <div data-slot="case-queue-table" className={className}>
      <SegmentedControl
        layout="inline"
        label="Show"
        options={QUEUE_FILTERS}
        value={filter}
        onValueChange={(value) => onFilterChange(value as QueueFilterValue)}
        className="mb-6"
      />
      <div
        aria-hidden="true"
        className={cn(
          COLUMNS,
          'h-10 border-b border-border text-small font-regular text-ink-muted max-sm:hidden',
        )}
      >
        <span>Person</span>
        <span>Category</span>
        <span>Sent</span>
        <span>Reply</span>
        <span>Status</span>
        <span />
      </div>
      {rows.length === 0 ? (
        <output className="block px-3 py-10 text-body text-ink-muted">{QUEUE_EMPTY[filter]}</output>
      ) : (
        // Explicit role: list-none drops list semantics in Safari and VoiceOver.
        // oxlint-disable-next-line jsx-a11y/no-redundant-roles
        <ul role="list" aria-label="Cases" className="m-0 list-none p-0">
          {rows.map((c) => {
            const name = `${c.givenName} ${c.familyName}`
            return (
              <li key={c.id}>
                <Link
                  to={`/cases/${c.id}`}
                  data-slot="case-queue-row"
                  data-own={c.isOwn || undefined}
                  aria-label={rowName(c, today, timeZone)}
                  className={cn(
                    COLUMNS,
                    'min-h-16 border-b border-border-subtle py-2.5 text-ink no-underline transition-colors hover:bg-primary-tint hover:text-ink',
                    'max-sm:gap-y-1.5 max-sm:px-4 max-sm:py-3.5',
                    'focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus-ring focus-visible:outline-solid',
                  )}
                >
                  <span className="flex min-w-0 items-center gap-3 max-sm:col-span-2">
                    <Avatar aria-hidden="true" size="row">
                      <AvatarFallback className="text-caption">{initialsOf(name)}</AvatarFallback>
                    </Avatar>
                    <span className="flex min-w-0 flex-col">
                      <span className="text-body font-semibold">{name}</span>
                      <span className="text-small/4.5 font-regular text-ink-muted">
                        {c.title} · {c.locationName}
                      </span>
                    </span>
                  </span>
                  <span className="flex min-w-0 flex-col gap-0.5 text-ui font-regular max-sm:col-span-2">
                    <span>{categoryLabel(c.category)}</span>
                    {c.crisis && (
                      <span className="flex items-start gap-1.5 text-small/4.5 font-regular text-ink-muted">
                        <Shield aria-hidden="true" className="mt-0.5 size-3.5 flex-none" />
                        {CRISIS_FACT}
                      </span>
                    )}
                  </span>
                  <span className="text-ui font-regular whitespace-nowrap text-ink-muted tabular-nums max-sm:hidden">
                    {dayInZone(c.sentAt, timeZone)}
                  </span>
                  <span className="text-ui font-regular text-ink tabular-nums">
                    {replyLine(c, today, timeZone)}
                  </span>
                  <span className="max-sm:justify-self-end">
                    <StatusBadge status={hrBadge(c.status)} />
                  </span>
                  <ChevronRight
                    data-slot="chevron"
                    aria-hidden="true"
                    className="size-4 text-ink-muted max-sm:hidden"
                  />
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

export { CaseQueueTable }
export type { CaseQueueTableProps }
