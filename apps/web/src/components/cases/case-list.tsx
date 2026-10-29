import type { CaseStatusOut } from '@/api/generated'
import { StatusBadge } from '@/components/timeoff/status-badge'
import { cn } from '@/lib/utils'
import { dayInZone } from './case-dates'
import { categoryLabel, EMPTY_CASE_LIST, personBadge, personDateLine } from './labels'
import { OpenCaseButton } from './open-case-button'

type CaseListProps = {
  /** The person's own cases, in the order to show them (the server orders them). */
  cases: CaseStatusOut[]
  /** The viewer's location's time zone, for the sent and status days. */
  timeZone: string
  /** The empty state's button. The page opens the form. */
  onOpenCase: () => void
  className?: string
}

/**
 * My cases (CaseList.jsx): status only. A row is not a link and never shows the person's words:
 * the category, the day it was sent, a badge, and a date line. Empty, it is a sunken card with
 * the one button that opens the form.
 */
function CaseList({ cases, timeZone, onOpenCase, className }: CaseListProps) {
  if (cases.length === 0) {
    return (
      <div
        data-slot="case-list-empty"
        className={cn(
          'flex flex-col items-start gap-4 rounded-lg border border-border bg-surface-sunken px-7 pt-7 pb-8 max-sm:px-4 max-sm:py-5',
          className,
        )}
      >
        <p className="m-0 text-body-lg">{EMPTY_CASE_LIST}</p>
        <OpenCaseButton onClick={onOpenCase} />
      </div>
    )
  }
  return (
    // Explicit role: list-none drops list semantics in Safari and VoiceOver.
    <ul
      role="list" // oxlint-disable-line jsx-a11y/no-redundant-roles
      aria-label="Your cases"
      data-slot="case-list"
      className={cn('m-0 list-none overflow-hidden rounded-lg border border-border p-0', className)}
    >
      {cases.map((c) => (
        <li
          key={c.id}
          className={cn(
            'grid grid-cols-[minmax(0,1fr)_248px_176px] items-center gap-4 px-5 py-4 not-first:border-t not-first:border-border-subtle',
            'max-sm:grid-cols-[minmax(0,1fr)_auto] max-sm:gap-y-1.5',
          )}
        >
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="text-body font-semibold text-ink">{categoryLabel(c.category)}</span>
            <span className="text-small text-ink-muted tabular-nums">
              Sent {dayInZone(c.sentAt, timeZone)}
            </span>
          </span>
          <span className="max-sm:col-start-2 max-sm:row-start-1">
            <StatusBadge status={personBadge(c.status)} />
          </span>
          <span className="text-right text-ui text-ink-muted tabular-nums max-sm:col-span-2 max-sm:row-start-2 max-sm:text-left">
            {personDateLine(c, timeZone)}
          </span>
        </li>
      ))}
    </ul>
  )
}

export { CaseList }
export type { CaseListProps }
