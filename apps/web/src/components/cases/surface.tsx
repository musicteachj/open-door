import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

type CaseSurfaceProps = ComponentProps<'div'> & {
  /**
   * `panel` is the band at the foot of an HR panel: full panel width, a confidential top border,
   * padding 22/24/24. `page` is the card on My cases, with a 16 px radius.
   */
  variant: 'panel' | 'page'
}

/**
 * The quiet aubergine wash the case form and its sent and limit lines sit on (cases.css:
 * .od-case-band and .od-case-card). Confidential, not alarming: never a warning color.
 */
function CaseSurface({ variant, className, ...props }: CaseSurfaceProps) {
  return (
    <div
      data-variant={variant}
      className={cn(
        'bg-confidential-tint',
        variant === 'panel'
          ? 'border-t border-confidential-border px-6 pt-5.5 pb-6 max-sm:px-4 max-sm:py-5'
          : 'rounded-xl border border-confidential-border px-7 pt-6 pb-7 max-sm:rounded-lg max-sm:px-4 max-sm:py-5',
        className,
      )}
      {...props}
    />
  )
}

export { CaseSurface }
export type { CaseSurfaceProps }
