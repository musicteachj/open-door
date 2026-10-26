import { Children, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

type RequestGroupProps = {
  title: string
  /** The line shown when the group has no rows: "No upcoming time off." */
  empty: string
  children?: ReactNode
  className?: string
}

/** A titled group of request rows ("Upcoming", "Past"), with an empty line when it has none. */
function RequestGroup({ title, empty, children, className }: RequestGroupProps) {
  const hasRows = Children.toArray(children).length > 0
  return (
    <div data-slot="request-group" className={cn('mt-6', className)}>
      <h3 className="m-0 border-b border-border px-3 pb-2 text-small font-semibold text-ink-muted">
        {title}
      </h3>
      {hasRows ? (
        <ul className="m-0 list-none p-0">{children}</ul>
      ) : (
        <p className="m-0 border-b border-border-subtle px-3 py-4 text-ui text-ink-muted">
          {empty}
        </p>
      )}
    </div>
  )
}

export { RequestGroup }
export type { RequestGroupProps }
