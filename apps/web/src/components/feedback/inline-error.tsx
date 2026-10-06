import { CircleAlert, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type InlineErrorProps = {
  message: string
  /** Shows a Retry button. Keep the user's input in place so Retry can resend it. */
  onRetry?: () => void
  className?: string
}

/**
 * Reports a failure right under the control that caused it, announced at once (`role="alert"`).
 * From InlineError.jsx. Errors never go in a toast; this is their home beside what failed.
 * An icon pairs with the text, so color is never the only signal.
 */
function InlineError({ message, onRetry, className }: InlineErrorProps) {
  return (
    <div
      data-slot="inline-error"
      role="alert"
      className={cn('mt-3 flex items-center gap-3 pr-1 pl-2', className)}
    >
      <p className="m-0 flex flex-1 items-center gap-2 text-ui text-danger">
        <CircleAlert data-slot="inline-error-icon" aria-hidden="true" className="size-4 shrink-0" />
        {message}
      </p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          <RotateCcw aria-hidden="true" className="size-4" />
          Retry
        </Button>
      )}
    </div>
  )
}

export { InlineError }
export type { InlineErrorProps }
