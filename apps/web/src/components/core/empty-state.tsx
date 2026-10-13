import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type EmptyStateProps = {
  message: string
  /** The one thing to do about it, such as "Clear filters". */
  action?: { label: string; onAction: () => void }
  /** A quieter second choice beside it, such as "Ask the assistant →". The icon follows the label. */
  secondaryAction?: { label: string; onAction: () => void; icon?: ReactNode }
  className?: string
}

/**
 * A message and one action, centered, for a list with nothing to show. From the directory's
 * empty frames in docs/design/system/Directory.dc.html. It is an `<output>` (a status), because
 * oxlint's jsx-a11y rule asks for that over `role="status"`.
 */
function EmptyState({ message, action, secondaryAction, className }: EmptyStateProps) {
  return (
    <output
      data-slot="empty-state"
      className={cn('flex flex-col items-center gap-4 py-18 text-center', className)}
    >
      <p className="text-body-lg text-ink">{message}</p>
      {(action || secondaryAction) && (
        <div className="flex flex-wrap justify-center gap-3">
          {action && (
            <Button variant="secondary" onClick={action.onAction}>
              {action.label}
            </Button>
          )}
          {secondaryAction && (
            <Button variant="ghost" className="pr-3.5 pl-4" onClick={secondaryAction.onAction}>
              {secondaryAction.label}
              {secondaryAction.icon}
            </Button>
          )}
        </div>
      )}
    </output>
  )
}

export { EmptyState }
export type { EmptyStateProps }
