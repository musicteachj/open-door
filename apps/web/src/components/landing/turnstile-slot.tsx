import type { ReactNode, Ref } from 'react'
import { cn } from '@/lib/utils'

type TurnstileSlotProps = {
  /** The element `getTurnstileToken` renders its widget into: hand it to `useStartSandbox`. */
  ref?: Ref<HTMLDivElement>
  className?: string
  /** For the gallery's stand-in only: the app's slot renders empty. */
  children?: ReactNode
}

/**
 * An empty place directly under a control that starts a sandbox. Cloudflare's Turnstile widget is
 * rendered into it when the control is pressed, and stays invisible unless Cloudflare needs a click,
 * and then its checkbox shows here, under the control that was pressed. It adds no margin of its
 * own: Cloudflare inserts a hidden container on every start, even when it shows nothing, so a
 * margin would make the page below jump each time. The element itself says nothing to a screen reader: the widget's own frame
 * carries its name.
 */
function TurnstileSlot({ ref, className, children }: TurnstileSlotProps) {
  return (
    <div ref={ref} data-slot="turnstile-slot" className={cn(className)}>
      {children}
    </div>
  )
}

export { TurnstileSlot }
export type { TurnstileSlotProps }
