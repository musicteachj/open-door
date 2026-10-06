import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { initialsOf } from '@/lib/initials'
import { directoryRowLabel } from '@/lib/labels'
import { cn } from '@/lib/utils'
import { directoryColumns } from './directory-grid'

type DirectoryRowProps = {
  name: string
  title: string
  department: string
  location: string
  /** The person's profile. */
  to: string
  /** Router state the profile reads, such as where the visitor came from. */
  linkState?: unknown
  initials?: string
  /** This is the signed-in person's own row. */
  isYou?: boolean
  className?: string
}

/**
 * One person in the directory, from DirectoryRow.jsx: a single link to their profile, named by
 * `directoryRowLabel`. The sketch gives the link `role="listitem"`, which would hide that it is a
 * link; the table's `li` carries the list semantics instead. The initials are decoration.
 */
function DirectoryRow({
  name,
  title,
  department,
  location,
  to,
  linkState,
  initials,
  isYou = false,
  className,
}: DirectoryRowProps) {
  return (
    <Link
      to={to}
      state={linkState}
      data-slot="directory-row"
      aria-label={directoryRowLabel({ name, title, department, location, isYou })}
      className={cn(
        directoryColumns,
        'h-15 border-b border-border-subtle text-ink no-underline transition-colors hover:bg-primary-tint hover:text-ink',
        'focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus-ring focus-visible:outline-solid',
        className,
      )}
    >
      <span className="flex min-w-0 items-center gap-3">
        <Avatar aria-hidden="true" className="size-8">
          <AvatarFallback className="text-caption">{initials ?? initialsOf(name)}</AvatarFallback>
        </Avatar>
        <span className="min-w-0 truncate text-body font-semibold">{name}</span>
        {isYou && (
          <span className="inline-flex h-5 flex-none items-center rounded-xs border border-border-strong px-1.5 text-caption text-ink-muted">
            You
          </span>
        )}
      </span>
      <span className="truncate text-ui font-regular max-[760px]:col-start-1 max-[760px]:pl-11">
        {title}
      </span>
      <span className="truncate text-ui font-regular text-ink-muted max-[760px]:col-start-1 max-[760px]:pl-11">
        {department}
      </span>
      <span className="truncate text-ui font-regular text-ink-muted max-[760px]:col-start-1 max-[760px]:pl-11">
        {location}
      </span>
      <ChevronRight
        aria-hidden="true"
        className="size-4 text-ink-muted max-[760px]:col-start-2 max-[760px]:row-start-1"
      />
    </Link>
  )
}

export { DirectoryRow }
export type { DirectoryRowProps }
