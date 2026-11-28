import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

/**
 * A placeholder bar for content on its way (docs/design/.../directory.css, .od-skel): 12 px
 * tall, 6 px corners, with a soft opacity pulse (ADR 0025) that stops under reduced motion. It is hidden from assistive technology; the region that is loading
 * carries the busy label. Shape it with className, like `size-8 rounded-full` for an avatar.
 */
function Skeleton({ className, ...props }: ComponentProps<'span'>) {
  return (
    <span
      data-slot="skeleton"
      aria-hidden="true"
      className={cn(
        'block h-3 rounded-xs bg-surface-hover motion-safe:animate-pulse-soft',
        className,
      )}
      {...props}
    />
  )
}

export { Skeleton }
