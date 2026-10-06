import { Tooltip as TooltipPrimitive } from 'radix-ui'
import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

/**
 * Short supplementary text on hover or focus. Use it only to reveal text that is cut off, or an
 * icon-only control's name. Never put essential information or an action in one.
 *
 * Keyboard focus opens it at once; hover waits 300 ms so a pointer passing over does not flash
 * it. It stays open while the pointer is over it, and Escape closes it (WCAG 1.4.13).
 */
function Tooltip({ delayDuration = 300, ...props }: ComponentProps<typeof TooltipPrimitive.Root>) {
  return (
    <TooltipPrimitive.Provider delayDuration={delayDuration}>
      <TooltipPrimitive.Root data-slot="tooltip" {...props} />
    </TooltipPrimitive.Provider>
  )
}

const TooltipTrigger = TooltipPrimitive.Trigger

function TooltipContent({
  className,
  sideOffset = 6,
  ...props
}: ComponentProps<typeof TooltipPrimitive.Content>) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        data-slot="tooltip-content"
        sideOffset={sideOffset}
        className={cn(
          'z-50 rounded-xs bg-tooltip-bg px-2.5 py-1.5 text-caption whitespace-nowrap text-tooltip-fg shadow-md',
          className,
        )}
        {...props}
      />
    </TooltipPrimitive.Portal>
  )
}

export { Tooltip, TooltipContent, TooltipTrigger }
