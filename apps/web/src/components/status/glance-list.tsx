import { useId } from 'react'
import { cn } from '@/lib/utils'
import { GlanceLink, type GlanceLinkProps } from './glance-link'

type GlanceItem = GlanceLinkProps & { id: string }

type GlanceListProps = {
  items: GlanceItem[]
  heading?: string
  className?: string
}

/** The "At a glance" list. With no items it renders nothing, not an empty heading. */
function GlanceList({ items, heading = 'At a glance', className }: GlanceListProps) {
  const headingId = useId()
  if (items.length === 0) return null
  return (
    <section
      data-slot="glance-list"
      aria-labelledby={headingId}
      className={cn('flex flex-col', className)}
    >
      <h2
        id={headingId}
        className="border-b border-border pb-3 text-small font-normal text-ink-muted"
      >
        {heading}
      </h2>
      <ul className="flex flex-col">
        {items.map(({ id, ...link }) => (
          <li key={id} className="flex flex-col">
            <GlanceLink {...link} />
          </li>
        ))}
      </ul>
    </section>
  )
}

export { GlanceList }
export type { GlanceItem, GlanceListProps }
