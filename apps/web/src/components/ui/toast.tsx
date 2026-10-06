import { CircleCheck, Info, X } from 'lucide-react'
import { Toast as ToastPrimitive } from 'radix-ui'
import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

const ToastProvider = ToastPrimitive.Provider

/** The bottom-right corner (the design's .od-toast-region). Mount one, inside the provider. */
function ToastViewport({ className, ...props }: ComponentProps<typeof ToastPrimitive.Viewport>) {
  return (
    <ToastPrimitive.Viewport
      data-slot="toast-viewport"
      className={cn(
        'fixed right-6 bottom-6 z-100 m-0 flex list-none flex-col gap-2 p-0',
        className,
      )}
      {...props}
    />
  )
}

const ICONS = { success: CircleCheck, info: Info }
const ICON_COLORS = { success: 'text-success', info: 'text-ink-muted' }

type ToastProps = ComponentProps<typeof ToastPrimitive.Root> & {
  tone?: 'success' | 'info'
}

/**
 * A short confirmation that something just happened: one sentence ending in a period, with an
 * icon and a Dismiss button. Closes after 6 seconds unless `duration` says otherwise, and Radix
 * pauses that clock while the pointer or focus is on it or the window is in the background.
 *
 * Confirmations only. Errors never go in a toast: it vanishes, and an error needs to stay beside
 * what failed (use the inline error). A polite status, so it never interrupts a screen reader.
 */
function Toast({ className, tone = 'success', duration = 6000, children, ...props }: ToastProps) {
  const Icon = ICONS[tone]
  return (
    <ToastPrimitive.Root
      data-slot="toast"
      type="background"
      duration={duration}
      className={cn(
        'flex max-w-110 min-w-80 items-center gap-3 rounded-md border border-border bg-surface-raised py-3 pr-2 pl-4 shadow-md',
        className,
      )}
      {...props}
    >
      <Icon
        data-slot="toast-icon"
        aria-hidden="true"
        className={cn('size-[18px] shrink-0', ICON_COLORS[tone])}
      />
      <ToastPrimitive.Description className="m-0 flex-1 text-ui font-regular text-ink">
        {children}
      </ToastPrimitive.Description>
      <ToastPrimitive.Close
        aria-label="Dismiss"
        className="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-sm text-ink-muted transition-colors hover:bg-neutral-hover hover:text-ink"
      >
        <X aria-hidden="true" className="size-4" />
      </ToastPrimitive.Close>
    </ToastPrimitive.Root>
  )
}

export { Toast, ToastProvider, ToastViewport }
