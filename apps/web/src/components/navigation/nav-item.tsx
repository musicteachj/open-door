import type { LucideIcon } from 'lucide-react'
import { Link, useMatch } from 'react-router'
import { cn } from '@/lib/utils'

type NavItemProps = {
  icon: LucideIcon
  label: string
  to: string
  /** The number waiting, such as Approvals' requests. Zero or none shows no badge. */
  count?: number
  /** What the count counts, in the link's name: "Approvals, 1 waiting", "Cases, 3 new". */
  countWord?: string
  /** Shows the word in the badge too ("3 new"), as the Cases item does. */
  wordInBadge?: boolean
  /** Forces the current look. By default an item is current when the route is its page or below it. */
  current?: boolean
  className?: string
}

/**
 * One link in the sidebar. The current page gets the tint and semibold; other items hover to
 * neutral-hover. The `ui` weight is 500, the unselected weight, so selected adds its own. A count
 * is in the link's name ("Approvals, 1 waiting") and shown as a badge. From NavItem.jsx.
 */
function NavItem({
  icon: Icon,
  label,
  to,
  count,
  countWord = 'waiting',
  wordInBadge = false,
  current,
  className,
}: NavItemProps) {
  const matches = useMatch({ path: to, end: false }) !== null
  const isCurrent = current ?? matches
  return (
    <Link
      to={to}
      aria-current={isCurrent ? 'page' : undefined}
      data-slot="nav-item"
      className={cn(
        // `relative` keeps the hidden text inside the link, so a scrolling nav clips it.
        'relative flex h-control items-center gap-3 rounded-md px-3 text-ui no-underline transition-[color,background-color]',
        isCurrent
          ? 'bg-primary-tint font-semibold text-ink hover:text-ink'
          : 'text-ink-nav hover:bg-neutral-hover hover:text-ink',
        className,
      )}
    >
      <Icon aria-hidden="true" className="size-4.5 flex-none" />
      <span className="min-w-0 flex-1 truncate">
        {label}
        {count ? (
          <span className="sr-only">
            , {count} {countWord}
          </span>
        ) : null}
      </span>
      {count ? (
        <span
          data-slot="nav-count"
          aria-hidden="true"
          className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-caption font-semibold text-on-primary tabular-nums"
        >
          {wordInBadge ? `${count} ${countWord}` : count}
        </span>
      ) : null}
    </Link>
  )
}

export { NavItem }
export type { NavItemProps }
