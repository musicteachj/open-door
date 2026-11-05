import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router'
import { cn } from '@/lib/utils'

type GlanceLinkProps = {
  /** The figure, such as "11.5". */
  value: string
  /** What the figure counts, such as "days PTO available". */
  label: string
  /** The name of where it goes, such as "Time off". */
  destination: string
  to: string
  /** A small dot beside the figure, for something that needs attention. Decoration only. */
  marker?: boolean
  className?: string
}

/**
 * One at-a-glance figure. The whole row is a single link, named by what it shows (the figure, what
 * it counts, and where it goes), which is what WCAG 2.5.3 asks for. From GlanceLink.jsx. The marker
 * sits in the figure's row, and is hidden from the name.
 */
function GlanceLink({ value, label, destination, to, marker = false, className }: GlanceLinkProps) {
  return (
    <Link
      to={to}
      data-slot="glance-link"
      className={cn(
        'group relative -mx-3 flex items-center gap-3 rounded-md border-b border-border-subtle px-3 py-5 text-ink no-underline transition-[color,background-color] hover:bg-primary-tint hover:text-ink focus-visible:z-10',
        className,
      )}
    >
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="flex items-center gap-2.5">
          <span className="text-numeric">{value}</span>
          {marker && (
            <span
              data-slot="glance-marker"
              aria-hidden="true"
              className="size-2 flex-none rounded-full bg-marker"
            />
          )}
        </span>{' '}
        <span className="text-ui text-ink-muted">{label}</span>
      </span>
      {/* Hidden words and pauses keep the name starting with what is shown: "11.5 days PTO available. Open Time off". */}
      <span className="sr-only">. Open</span>{' '}
      <span className="flex items-center gap-1 text-small font-semibold text-primary underline-offset-3 group-hover:underline">
        {destination}
        <ChevronRight aria-hidden="true" className="size-4" />
      </span>
    </Link>
  )
}

export { GlanceLink }
export type { GlanceLinkProps }
