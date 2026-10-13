import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router'
import type { SectionSummary } from '@/api/generated'
import { rowFocusRing } from '@/components/ui/focus-ring'
import { cn } from '@/lib/utils'
import { ApplicabilityBadge } from './applicability-badge'
import { AppliesMarker } from './applies-marker'
import { LastUpdated } from './last-updated'
import { handbookPath, markerShownInList, sectionRowLabel } from './labels'

/** The list's columns (.od-sec-cols): number, title, audience, marker, date, chevron. */
const sectionColumns =
  'grid grid-cols-[72px_minmax(0,1fr)_220px_136px_128px_16px] items-center gap-x-5 px-3 @max-[56rem]:grid-cols-[3.5rem_minmax(0,1fr)_16px] @max-[56rem]:gap-x-3 @max-[56rem]:gap-y-0.5'

type SectionRowProps = {
  section: SectionSummary
  /** This is the section being read; the row is tinted and marked `aria-current="page"`. */
  current?: boolean
  className?: string
}

/**
 * One handbook section in the table of contents, from SectionRow.jsx: a single link named by
 * `sectionRowLabel`. The marker shows only when the section covers the person and its audience is
 * restricted (`markerShownInList`). It renders the `li`, so it belongs inside a `SectionGroup`'s
 * list. The sketch's `onOpen` and `href` become a router `Link`. No arrow-key handling: rows are
 * plain links in the Tab order.
 */
function SectionRow({ section, current = false, className }: SectionRowProps) {
  const markerShown = markerShownInList(section)
  return (
    <li className="@container">
      <Link
        to={handbookPath(section.id)}
        data-slot="section-row"
        aria-current={current ? 'page' : undefined}
        aria-label={sectionRowLabel(section, markerShown)}
        className={cn(
          sectionColumns,
          'min-h-12 border-b border-border-subtle text-ink no-underline transition-colors hover:bg-primary-tint hover:text-ink',
          rowFocusRing,
          current && 'bg-primary-tint',
          className,
        )}
      >
        <span className="text-ui font-regular text-ink-muted tabular-nums @max-[56rem]:col-start-1">
          {section.id}
        </span>
        <span
          className={cn(
            'py-3 text-body font-regular @max-[56rem]:col-start-2 @max-[56rem]:row-start-1 @max-[56rem]:py-0',
            current && 'font-semibold',
          )}
        >
          {section.title}
        </span>
        <ApplicabilityBadge
          label={section.audienceLabel}
          variant="text"
          className="@max-[56rem]:col-start-2"
        />
        <span className="@max-[56rem]:col-start-2">{markerShown && <AppliesMarker applies />}</span>
        <LastUpdated date={section.lastUpdated} bare className="text-ui @max-[56rem]:col-start-2" />
        <ChevronRight
          aria-hidden="true"
          className="size-4 text-ink-muted @max-[56rem]:col-start-3 @max-[56rem]:row-span-2 @max-[56rem]:row-start-1"
        />
      </Link>
    </li>
  )
}

export { SectionRow }
export type { SectionRowProps }
