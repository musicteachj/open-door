import { RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'

type ConsoleErrorProps = {
  /** The response's request ID. Left out for a network failure, which has none. */
  reference?: string
  onRetry: () => void
}

/**
 * Global States' "Something went wrong on our side." inside the console's own section
 * (screen 13, desktop-error). It is the same pattern as `SomethingWentWrong`, but a section's
 * heading rather than a page's `h1`, and it takes no focus: the scoreboard below stays usable.
 */
function ConsoleError({ reference, onRetry }: ConsoleErrorProps) {
  return (
    <div
      role="alert"
      data-slot="console-error"
      className="flex min-h-100 flex-col items-center justify-center gap-3 py-16 text-center"
    >
      <h3 className="m-0 text-h1 text-balance text-ink">Something went wrong on our side.</h3>
      <p className="m-0 max-w-110 text-body text-pretty text-ink-muted">
        {reference
          ? 'The sandbox figures didn’t load. Try again in a moment. If it keeps happening, this reference helps us find it:'
          : 'The sandbox figures didn’t load. Try again in a moment.'}
      </p>
      {reference && (
        <p className="m-0 flex flex-wrap items-center justify-center gap-2 text-small text-ink-muted">
          Reference
          <code className="rounded-xs border border-border bg-surface-sunken px-2 py-0.5 font-mono text-small break-all text-ink select-all">
            {reference}
          </code>
        </p>
      )}
      <Button className="mt-3" onClick={onRetry}>
        <RotateCcw aria-hidden="true" className="size-4" />
        Retry
      </Button>
    </div>
  )
}

export { ConsoleError }
export type { ConsoleErrorProps }
