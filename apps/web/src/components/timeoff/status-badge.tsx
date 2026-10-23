import { Ban, CircleCheck, CircleX, ClipboardCheck, Clock, type LucideIcon } from 'lucide-react'
import type { RequestOutStatus } from '@/api/generated'
import { cn } from '@/lib/utils'
import { statusLabel, type TimeOffStatus } from './labels'

type StatusBadgeProps = {
  /** A request's status. The API's `pending` reads as `waiting`. */
  status: TimeOffStatus | RequestOutStatus
  className?: string
}

const ICONS: Record<TimeOffStatus, { icon: LucideIcon; className: string }> = {
  waiting: { icon: Clock, className: 'text-marker' },
  approved: { icon: CircleCheck, className: 'text-success' },
  // Ink, never red: a denial is a decision, not an error.
  denied: { icon: CircleX, className: 'text-ink' },
  recorded: { icon: ClipboardCheck, className: 'text-success' },
  canceled: { icon: Ban, className: 'text-ink-muted' },
}

function normalize(status: TimeOffStatus | RequestOutStatus): TimeOffStatus {
  return status === 'pending' ? 'waiting' : status
}

/**
 * A request's status as an icon and a fixed word (StatusBadge.jsx), so color is never the only
 * signal. Canceled is muted all through.
 */
function StatusBadge({ status, className }: StatusBadgeProps) {
  const key = normalize(status)
  const { icon: Icon, className: iconClass } = ICONS[key]
  return (
    <span
      data-slot="status-badge"
      data-status={key}
      className={cn(
        'inline-flex h-6 items-center gap-1.5 rounded-xs border border-border-strong bg-surface-raised px-2 text-small font-medium whitespace-nowrap',
        key === 'canceled' ? 'text-ink-muted' : 'text-ink',
        className,
      )}
    >
      <Icon aria-hidden="true" strokeWidth={2} className={cn('size-3.5', iconClass)} />
      {statusLabel(key)}
    </span>
  )
}

export { StatusBadge }
export type { StatusBadgeProps }
