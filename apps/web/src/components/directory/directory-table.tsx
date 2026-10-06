import { useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { directoryColumns } from './directory-grid'
import { DirectoryRow, type DirectoryRowProps } from './directory-row'
import { SkeletonRow } from './skeleton-row'

type DirectoryItem = DirectoryRowProps & { id: string }

type DirectoryTableProps = {
  items: DirectoryItem[]
  /** Eight skeleton rows stand in for the list, and the labels stay. */
  loading?: boolean
  /** The signed-in person's ID, to tag their own row. */
  youId?: string
  className?: string
}

/**
 * The people list, from DirectoryTable.jsx: column labels, then one link per person, or eight
 * skeleton rows while loading. The labels are visual only (hidden from screen readers, and from
 * narrow screens, where rows stack), as in the sketch: each row's link name already says name,
 * title, department, and location, so a header row with no table semantics would only repeat them.
 * The empty state, "Showing 50 of 120", and "Show more" belong to the page.
 */
function DirectoryTable({ items, loading = false, youId, className }: DirectoryTableProps) {
  // A live region announces changes made after it is in the page, not text that arrives with it.
  // A page usually mounts the table already loading, so the status starts empty and is filled
  // in an effect, which makes the text a change. React renders the region with no children, so
  // writing its text through the ref doesn't fight a render.
  const statusRef = useRef<HTMLOutputElement>(null)
  useEffect(() => {
    if (statusRef.current) statusRef.current.textContent = loading ? 'Loading the directory' : ''
  }, [loading])
  return (
    <div data-slot="directory-table" className={className}>
      {/* Outside the busy region, which may mute live content, and always mounted. */}
      <output ref={statusRef} className="sr-only" />
      <div aria-busy={loading}>
        <div
          aria-hidden="true"
          className={cn(
            directoryColumns,
            'h-10 border-b border-border text-small text-ink-muted max-[760px]:hidden',
          )}
        >
          <span>Name</span>
          <span>Title</span>
          <span>Department</span>
          <span>Location</span>
          <span />
        </div>
        {loading ? (
          <>
            {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
              <SkeletonRow key={i} variant={i} />
            ))}
          </>
        ) : (
          items.length > 0 && (
            // Explicit role: list-none drops list semantics in Safari and VoiceOver.
            // oxlint-disable-next-line jsx-a11y/no-redundant-roles
            <ul role="list" aria-label="People" className="m-0 list-none p-0">
              {items.map(({ id, ...row }) => (
                <li key={id}>
                  <DirectoryRow {...row} isYou={id === youId} />
                </li>
              ))}
            </ul>
          )
        )}
      </div>
    </div>
  )
}

export { DirectoryTable }
export type { DirectoryItem, DirectoryTableProps }
