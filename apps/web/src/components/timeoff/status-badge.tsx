import {
  Ban,
  CircleCheck,
  CircleX,
  ClipboardCheck,
  Clock,
  FileSearch,
  type LucideIcon,
} from 'lucide-react'
import type { RequestOutStatus } from '@/api/generated'
import { CASE_BADGE_WORDS, isCaseBadge, type CaseBadge } from '@/components/status/case-badges'
import { cn } from '@/lib/utils'
import { statusLabel, type TimeOffStatus } from './labels'

type StatusBadgeProps = {
  /**
   * A request's status (the API's `pending` reads as `waiting`), or a case's: `personBadge` and
   * `hrBadge` in `components/cases/labels` map the API's status to the right one.
   */
  status: TimeOffStatus | RequestOutStatus | CaseBadge
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

// A case's icons. A new case has no icon: a small filled cinnamon dot, the same "waiting" signal.
// Finished and closed are neutral ink, never a success green: a closed case is not a good outcome.
const CASE_ICONS: Record<
  Exclude<CaseBadge, 'case-new'>,
  { icon: LucideIcon; className: string }
> = {
  'case-sent': { icon: Clock, className: 'text-marker' },
  'case-reviewing': { icon: FileSearch, className: 'text-primary' },
  'case-finished': { icon: CircleCheck, className: 'text-ink' },
  'case-in-review': { icon: FileSearch, className: 'text-primary' },
  'case-closed': { icon: CircleCheck, className: 'text-ink' },
}

function normalize(status: TimeOffStatus | RequestOutStatus | CaseBadge) {
  return status === 'pending' ? 'waiting' : status
}

function RequestIcon({ status }: { status: TimeOffStatus }) {
  const { icon: Icon, className } = ICONS[status]
  return <Icon aria-hidden="true" strokeWidth={2} className={cn('size-3.5', className)} />
}

function CaseIcon({ status }: { status: Exclude<CaseBadge, 'case-new'> }) {
  const { icon: Icon, className } = CASE_ICONS[status]
  return <Icon aria-hidden="true" strokeWidth={2} className={cn('size-3.5', className)} />
}

/**
 * A status as an icon and a fixed word (StatusBadge.jsx), so color is never the only signal.
 * Canceled is muted all through.
 */
function StatusBadge({ status, className }: StatusBadgeProps) {
  const key = normalize(status)
  const mark = isCaseBadge(key) ? (
    key === 'case-new' ? (
      <span
        data-slot="status-dot"
        aria-hidden="true"
        className="mx-0.5 size-1.5 rounded-full bg-marker"
      />
    ) : (
      <CaseIcon status={key} />
    )
  ) : (
    <RequestIcon status={key} />
  )
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
      {mark}
      {isCaseBadge(key) ? CASE_BADGE_WORDS[key] : statusLabel(key)}
    </span>
  )
}

export { StatusBadge }
export type { StatusBadgeProps }
