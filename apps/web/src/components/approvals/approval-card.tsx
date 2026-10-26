import { useState } from 'react'
import type { RequestOut, RequestOutStatus } from '@/api/generated'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { FormMessage } from '@/components/timeoff/form-message'
import { StatusBadge } from '@/components/timeoff/status-badge'
import { longRange } from '@/components/timeoff/dates'
import { availableAfter } from '@/components/timeoff/labels'
import { initialsOf } from '@/lib/initials'
import { cn } from '@/lib/utils'
import { CoverageLine } from './coverage-line'
import { actionName, approvalsCopy, conflictText, firstNameOf, sentLine } from './labels'

type ApprovalCardProps =
  | { loading: true; className?: string }
  | {
      loading?: false
      /** A waiting PTO request, with its `availableAfterLabel` and `coverage` as the API sends them. */
      request: RequestOut
      /** Today in the location's time zone, "YYYY-MM-DD", and that zone, for "Sent today". */
      today: string
      timeZone: string
      /**
       * Set when the request has moved on (canceled, or decided already): the card is muted, shows
       * this status in place of the sent date, has no buttons, and says why as an alert.
       */
      conflict?: RequestOutStatus
      /** Called with the request and the button, so the page can return focus to it. */
      onApprove?: (request: RequestOut, button: HTMLButtonElement) => void
      onDeny?: (request: RequestOut, button: HTMLButtonElement) => void
      className?: string
    }

const cardClass =
  'flex flex-col gap-4 rounded-lg border border-border bg-surface-raised px-6 py-5 text-ink max-sm:p-4'

/**
 * A waiting request for its manager to decide (ApprovalCard.jsx): who, when it was sent, the dates,
 * the amount, the balance after, and plain team coverage. Approve and Deny are both secondary and
 * the same size, Approve first, so neither is favored (invariant 5). A list item: put it in a
 * `ul`. Every figure is the API's label.
 */
function ApprovalCard(props: ApprovalCardProps) {
  // The refusal is announced only when a card seen waiting turns into a conflict while on the page,
  // not when a card is first drawn already a conflict (or after its skeleton).
  const [announce, setAnnounce] = useState(false)
  if (!props.loading && props.conflict === undefined && !announce) setAnnounce(true)
  if (props.loading) {
    return (
      <li
        data-slot="approval-card"
        data-state="loading"
        aria-hidden="true"
        className={cn(cardClass, props.className)}
      >
        <div className="flex items-center gap-3">
          <Skeleton className="size-10 rounded-full" />
          <div className="flex flex-col gap-2">
            <Skeleton className="w-30" />
            <Skeleton className="h-2.5 w-42" />
          </div>
        </div>
        <div className="flex flex-col gap-2.5 border-t border-border-subtle pt-4">
          <Skeleton className="h-3.5 w-90 max-w-full" />
          <Skeleton className="h-2.5 w-45" />
          <Skeleton className="h-2.5 w-65 max-w-full" />
        </div>
      </li>
    )
  }
  const { request, today, timeZone, conflict, onApprove, onDeny, className } = props
  const muted = conflict !== undefined
  const first = firstNameOf(request.person.name)
  const multiDay = request.startDate !== request.endDate
  return (
    <li
      data-slot="approval-card"
      data-request-id={request.id}
      data-state={muted ? 'conflict' : 'default'}
      className={cn(cardClass, muted && 'bg-surface-sunken', className)}
    >
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 max-sm:flex-col max-sm:items-start">
        <div className="flex min-w-0 items-center gap-3">
          <Avatar size="lg" muted={muted} aria-hidden="true">
            <AvatarFallback>{initialsOf(request.person.name)}</AvatarFallback>
          </Avatar>
          <div className="flex min-w-0 flex-col">
            <h3
              className={cn('m-0 text-body font-semibold', muted ? 'text-ink-muted' : 'text-ink')}
            >
              {request.person.name}
            </h3>
            <span className="text-small text-ink-muted">{request.person.title}</span>
          </div>
        </div>
        {muted ? (
          <StatusBadge status={conflict} />
        ) : (
          <span className="text-small text-ink-muted tabular-nums">
            {sentLine(request.createdAt, today, timeZone)}
          </span>
        )}
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-end gap-x-8 gap-y-4 border-t border-border-subtle pt-4 max-sm:grid-cols-[minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-0.5 tabular-nums">
          <p
            className={cn(
              // The design's dates are 17/26 semibold; no type token matches it.
              'm-0 text-[17px]/6.5 font-semibold text-pretty',
              muted && 'text-ink-muted',
            )}
          >
            {longRange(request.startDate, request.endDate)}
          </p>
          <p className="m-0 text-ui text-ink-muted">PTO · {request.amountLabel}</p>
          {request.availableAfterLabel && (
            <p className={cn('m-0 text-ui', muted && 'text-ink-muted')}>
              {availableAfter(request.availableAfterLabel)}
            </p>
          )}
          <CoverageLine
            coverage={request.coverage}
            multiDay={multiDay}
            muted={muted}
            className="mt-3"
          />
        </div>
        {!muted && (
          <div className="flex gap-3 max-sm:grid max-sm:grid-cols-2">
            <Button
              variant="secondary"
              aria-label={actionName('approve', request.person, request.startDate, request.endDate)}
              onClick={(event) => onApprove?.(request, event.currentTarget)}
            >
              {approvalsCopy.approve}
            </Button>
            <Button
              variant="secondary"
              aria-label={actionName('deny', request.person, request.startDate, request.endDate)}
              onClick={(event) => onDeny?.(request, event.currentTarget)}
            >
              {approvalsCopy.deny}
            </Button>
          </div>
        )}
      </div>
      {muted && (
        <FormMessage tone="refusal" announce={announce}>
          {conflictText(conflict, first)}
        </FormMessage>
      )}
    </li>
  )
}

export { ApprovalCard }
export type { ApprovalCardProps }
