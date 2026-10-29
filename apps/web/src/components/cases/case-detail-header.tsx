import { History, Lock, Shield } from 'lucide-react'
import type { Ref } from 'react'
import type { Category, Status } from '@/api/generated'
import { StatusBadge } from '@/components/timeoff/status-badge'
import { cn } from '@/lib/utils'
import { dateTimeInZone } from './case-dates'
import { categoryLabel, CRISIS_FACT, detailCopy, hrBadge, replyLine } from './labels'

type CaseDetailHeaderProps = {
  category: Category
  status: Status
  /** UTC timestamps, shown in `timeZone`. */
  sentAt: string
  statusChangedAt: string
  /** A calendar date. */
  replyBy: string
  timeZone: string
  /** Today's calendar date in the viewer's location, so an overdue reply reads as the queue says it. */
  today: string
  /** The safety check routed this case to crisis text. */
  crisis: boolean
  /** HR's own case: metadata only, and no promise that reads are recorded. */
  isOwn: boolean
  /** The page moves focus to the heading after a case is closed. */
  headingRef?: Ref<HTMLHeadingElement>
  className?: string
}

/**
 * A case's heading and facts: the lock, the category as the page's h1 (focusable by script), HR's
 * badge, the dates line, the crisis fact when it applies, and the line that every read of the case
 * is recorded. The crisis fact is a fact in muted ink, never an alert.
 */
function CaseDetailHeader({
  category,
  status,
  sentAt,
  statusChangedAt,
  replyBy,
  timeZone,
  today,
  crisis,
  isOwn,
  headingRef,
  className,
}: CaseDetailHeaderProps) {
  const progress = replyLine({ status, replyBy, statusChangedAt }, today, timeZone)
  return (
    <header data-slot="case-detail-header" className={cn('flex flex-col gap-2', className)}>
      {/* The lock stays beside the heading's first line when a long category wraps. */}
      <div className="flex items-start gap-3">
        <Lock aria-hidden="true" className="mt-1 size-7 shrink-0 text-primary" />
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2">
          <h1 ref={headingRef} tabIndex={-1} className="m-0 text-h1 outline-none">
            {categoryLabel(category)}
          </h1>
          <StatusBadge status={hrBadge(status)} />
        </div>
      </div>
      <p data-slot="case-dates" className="m-0 text-body">
        Sent {dateTimeInZone(sentAt, timeZone)} <span aria-hidden="true">·</span>{' '}
        <span className="sr-only">. </span>
        {progress}
      </p>
      {crisis && (
        <p className="m-0 flex items-center gap-2 text-ui font-regular text-ink-muted">
          <Shield aria-hidden="true" className="size-3.5 flex-none" />
          {CRISIS_FACT}
        </p>
      )}
      {!isOwn && (
        <p className="m-0 flex items-center gap-2 text-small text-ink-muted">
          <History aria-hidden="true" className="size-3.5 flex-none" />
          {detailCopy.readsRecorded}
        </p>
      )}
    </header>
  )
}

export { CaseDetailHeader }
export type { CaseDetailHeaderProps }
