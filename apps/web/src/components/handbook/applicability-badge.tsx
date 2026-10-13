import { handbookCopy } from './labels'
import { cn } from '@/lib/utils'

type ApplicabilityBadgeProps = {
  /** The API's `audienceLabel`: "Everyone", "California employees", "Hourly staff in California". */
  label: string
  /** The chip reads "Applies to: …"; the text variant is the bare value for the list column. */
  variant?: 'chip' | 'text'
  className?: string
}

/**
 * Who a handbook section applies to, from ApplicabilityBadge.jsx. The sketch builds its label from
 * a state, a type, and a location; here the server has built it already (`audienceLabel`), so the
 * browser never rebuilds it.
 */
function ApplicabilityBadge({ label, variant = 'chip', className }: ApplicabilityBadgeProps) {
  if (variant === 'text') {
    return <span className={cn('text-ui font-regular text-ink-muted', className)}>{label}</span>
  }
  return (
    <span
      className={cn(
        'inline-flex h-6 items-center gap-[5px] rounded-xs border border-border-strong px-2 text-small font-regular whitespace-nowrap text-ink',
        className,
      )}
    >
      <span className="text-ink-muted">{handbookCopy.appliesPrefix}</span>
      <span className="font-semibold">{label}</span>
    </span>
  )
}

export { ApplicabilityBadge }
export type { ApplicabilityBadgeProps }
