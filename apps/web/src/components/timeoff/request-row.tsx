import type { RequestOut } from '@/api/generated'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { initialsOf } from '@/lib/initials'
import { cn } from '@/lib/utils'
import { longRange } from './dates'
import { StatusBadge } from './status-badge'
import { typeLabel } from './labels'

type RequestRowProps = {
  request: RequestOut
  /** `mine` is the caller's own row, with Cancel. `team` is someone else's, with a person column. */
  variant: 'mine' | 'team'
  /** Whether the caller may cancel this request (mine only). The server decides; this shows it. */
  canCancel?: boolean
  /** Called with the request and the button, so the page can return focus to it. */
  onCancel?: (request: RequestOut, button: HTMLButtonElement) => void
  /** Team rows: "Approved October 5", "Denied today". */
  decidedLine?: string | null
  /** Team rows: "Your note". Mine reads "Marcus Bell's note" from the decider. */
  noteLabel?: string
  className?: string
}

/**
 * One request in a list (RequestRow.jsx). The dates lead, then "PTO · 8 hours (1 day)", then the
 * status badge with who decided under it. A denial's note sits under the row. The amount is the
 * API's label. The row tints on hover and while anything inside has focus; below 640 px it stacks,
 * with Cancel at the top right and the badge under the dates.
 */
function RequestRow({
  request,
  variant,
  canCancel = false,
  onCancel,
  decidedLine,
  noteLabel,
  className,
}: RequestRowProps) {
  const team = variant === 'team'
  const dates = longRange(request.startDate, request.endDate)
  const word = typeLabel(request.type)
  const decided = request.status === 'approved' || request.status === 'denied'
  const by =
    decidedLine ??
    (!team && decided && request.decidedBy
      ? `${request.status === 'denied' ? 'Denied' : 'Approved'} by ${request.decidedBy.name}`
      : null)
  const note = request.decisionNote
  const label = noteLabel ?? (request.decidedBy ? `${request.decidedBy.name}’s note` : 'Note')
  return (
    <li
      data-slot="request-row"
      data-variant={variant}
      className={cn(
        'grid items-center gap-x-6 gap-y-2.5 border-b border-border-subtle px-3 py-3.5 text-ink transition-colors',
        'focus-within:bg-surface-sunken hover:bg-surface-sunken',
        team
          ? 'grid-cols-[minmax(0,220px)_minmax(0,1fr)_minmax(0,220px)] max-sm:grid-cols-[minmax(0,1fr)]'
          : 'grid-cols-[minmax(0,1fr)_minmax(0,240px)_96px] max-sm:grid-cols-[minmax(0,1fr)_auto]',
        className,
      )}
    >
      {team && (
        <div className="flex min-w-0 items-center gap-2.5 text-ui font-semibold">
          <Avatar size="row" aria-hidden="true">
            <AvatarFallback>{initialsOf(request.person.name)}</AvatarFallback>
          </Avatar>
          <span className="min-w-0">{request.person.name}</span>
        </div>
      )}
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="text-body font-semibold tabular-nums">{dates}</span>
        <span className="text-ui text-ink-muted tabular-nums">
          {word} · {request.amountLabel}
        </span>
      </div>
      <div
        className={cn(
          'flex min-w-0 flex-col items-start gap-1',
          !team && 'max-sm:col-start-1 max-sm:row-start-2',
        )}
      >
        <StatusBadge status={request.status} />
        {by && <span className="text-small text-ink-muted">{by}</span>}
      </div>
      {!team && (
        <div className="flex justify-end max-sm:col-start-2 max-sm:row-span-2 max-sm:row-start-1 max-sm:self-start">
          {canCancel && (
            <Button
              variant="secondary"
              size="sm"
              aria-label={`Cancel ${typeLabel(request.type, { lower: true })} on ${dates}`}
              onClick={(event) => onCancel?.(request, event.currentTarget)}
            >
              Cancel
            </Button>
          )}
        </div>
      )}
      {note && (
        <div
          className={cn(
            'flex max-w-150 flex-col gap-0.5 rounded-md border border-border-subtle bg-surface-sunken px-3.5 py-2.5',
            team ? 'col-[2/-1] max-sm:col-[1/-1]' : 'col-[1/-1]',
          )}
        >
          <span className="text-small text-ink-muted">{label}</span>
          <p className="m-0 text-ui/5.5 text-pretty">“{note}”</p>
        </div>
      )}
    </li>
  )
}

export { RequestRow }
export type { RequestRowProps }
