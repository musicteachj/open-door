import { Lock } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

type DetailRowProps = { label: string; className?: string } & (
  | {
      /** A plain value, or (as children) a link such as the manager's profile. */
      locked?: false
      value?: string
      children?: ReactNode
      reason?: never
    }
  | {
      /** The viewer may not see this field. The row says who can, and never holds the value. */
      locked: true
      /** Why, from the person's given name: "Visible to Leo and HR". */
      reason: string
      value?: never
      children?: never
    }
)

/**
 * One field on a profile, from DetailRow.jsx: a term and its description. A locked row is built
 * from the field name and the reason alone, so a value can't reach the page; it is a muted lock
 * and the reason (the lock never carries the meaning alone), with no warning color.
 */
function DetailRow(props: DetailRowProps) {
  const { label, className } = props
  return (
    <div
      data-slot="detail-row"
      className={cn(
        'grid grid-cols-[calc(var(--spacing)*34)_minmax(0,1fr)] items-baseline gap-4 border-b border-border-subtle py-3.5 last:border-b-0',
        'max-[760px]:grid-cols-1 max-[760px]:gap-0.5',
        className,
      )}
    >
      <dt className="text-ui font-regular text-ink-muted">{label}</dt>
      <dd className="m-0 min-w-0 text-body [overflow-wrap:anywhere] [&_a]:underline [&_a]:decoration-1 [&_a]:underline-offset-3">
        {props.locked ? (
          <span className="inline-flex items-center gap-1.5 text-ui font-regular text-ink-muted">
            <Lock aria-hidden="true" className="size-3.5" />
            {props.reason}
            <span className="sr-only">. Value hidden.</span>
          </span>
        ) : (
          (props.children ?? props.value)
        )}
      </dd>
    </div>
  )
}

export { DetailRow }
export type { DetailRowProps }
