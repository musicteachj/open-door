import { Check, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'
import { handbookCopy } from './labels'

type AppliesMarkerProps = {
  applies: boolean
  className?: string
}

/**
 * Whether a section applies to the signed-in person, from AppliesMarker.jsx. Always an icon plus
 * words, so color is never the only signal; "no" is muted, never a warning.
 */
function AppliesMarker({ applies, className }: AppliesMarkerProps) {
  const Icon = applies ? Check : Minus
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 text-small font-regular whitespace-nowrap',
        applies ? 'text-ink' : 'text-ink-muted',
        className,
      )}
    >
      <Icon
        aria-hidden="true"
        strokeWidth={2}
        className={cn('size-3.5', applies && 'text-primary')}
      />
      {applies ? handbookCopy.marker.yes : handbookCopy.marker.no}
    </span>
  )
}

export { AppliesMarker }
export type { AppliesMarkerProps }
