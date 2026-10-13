import { ChevronRight } from 'lucide-react'
import { useId } from 'react'
import { Link } from 'react-router'
import type { SectionRef } from '@/api/generated'
import { rowFocusRing } from '@/components/ui/focus-ring'
import { cn } from '@/lib/utils'
import { AppliesMarker } from './applies-marker'
import { handbookCopy, handbookPath } from './labels'

type LinkBlockProps = {
  /** "State rules" on a company section (its addenda), "Supplements" on an addendum (its company section). */
  variant: 'stateRules' | 'supplements'
  /** A note beside the title, such as "California and Colorado add to this section." */
  note?: string
  sections: SectionRef[]
  className?: string
}

/**
 * The bordered block that links a company section and its state addenda both ways (LinkBlock.jsx).
 * The sketch takes ready-made links; this takes the API's `SectionRef`s and builds the rows. A
 * state-rules row is "California addendum · CA-4.3" with the name in ink, the ID muted, and the
 * applies marker only where the section applies to the person (the sketch's `appliesToYou &&`).
 * The supplements row is "§4.3 Sick leave · Company handbook", with no marker. Renders nothing
 * with no rows.
 */
function LinkBlock({ variant, note, sections, className }: LinkBlockProps) {
  const headingId = useId()
  if (sections.length === 0) return null
  const stateRules = variant === 'stateRules'
  const title = stateRules ? handbookCopy.stateRules : handbookCopy.supplements
  return (
    <section
      aria-labelledby={headingId}
      className={cn('@container rounded-lg border border-border', className)}
    >
      <div className="flex flex-wrap items-baseline gap-2.5 px-4 pt-3 pb-1.5">
        <h2 id={headingId} className="m-0 text-small font-semibold">
          {title}
        </h2>
        {note && <span className="text-small text-ink-muted">{note}</span>}
      </div>
      <ul className="m-0 list-none p-1 pt-0">
        {sections.map((section) => (
          <li key={section.id}>
            <Link
              to={handbookPath(section.id)}
              className={cn(
                'grid min-h-11 grid-cols-[minmax(0,1fr)_auto_16px] items-center gap-x-3 rounded-md px-3 text-body text-ink no-underline transition-colors hover:bg-primary-tint hover:text-ink',
                // In a narrow block the marker moves under the name, as the section rows do.
                '@max-[30rem]:grid-cols-[minmax(0,1fr)_16px] @max-[30rem]:py-2',
                rowFocusRing,
              )}
            >
              <span className="col-start-1 row-start-1 min-w-0">
                {stateRules ? (
                  <>
                    {section.groupName}
                    <span className="whitespace-nowrap text-ink-muted"> · {section.id}</span>
                  </>
                ) : (
                  <>
                    §{section.id} {section.title}
                    <span className="text-ink-muted"> · {handbookCopy.companyHandbook}</span>
                  </>
                )}
              </span>
              {stateRules && section.appliesToMe && (
                <AppliesMarker
                  applies
                  className="col-start-2 row-start-1 @max-[30rem]:col-start-1 @max-[30rem]:row-start-2"
                />
              )}
              <ChevronRight
                aria-hidden="true"
                className="col-start-3 row-start-1 size-4 text-ink-muted @max-[30rem]:col-start-2 @max-[30rem]:row-span-2"
              />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

export { LinkBlock }
export type { LinkBlockProps }
