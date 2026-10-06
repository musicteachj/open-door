import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type EmptyStateProps = {
  message: string
  /** The one thing to do about it, such as "Clear filters". */
  action?: { label: string; onAction: () => void }
  className?: string
}

/**
 * A message and one action, centered, for a list with nothing to show. From the directory's
 * empty frames in docs/design/system/Directory.dc.html. It is an `<output>` (a status), because
 * oxlint's jsx-a11y rule asks for that over `role="status"`.
 */
function EmptyState({ message, action, className }: EmptyStateProps) {
  return (
    <output
      data-slot="empty-state"
      className={cn('flex flex-col items-center gap-4 py-18 text-center', className)}
    >
      <p className="text-body-lg text-ink">{message}</p>
      {action && (
        <Button variant="secondary" onClick={action.onAction}>
          {action.label}
        </Button>
      )}
    </output>
  )
}

export { EmptyState }
export type { EmptyStateProps }
