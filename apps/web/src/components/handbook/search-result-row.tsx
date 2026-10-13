import { Fragment, useId } from 'react'
import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router'
import type { SearchResultOut } from '@/api/generated'
import { rowFocusRing } from '@/components/ui/focus-ring'
import { cn } from '@/lib/utils'
import { ApplicabilityBadge } from './applicability-badge'
import { AppliesMarker } from './applies-marker'
import { LastUpdated } from './last-updated'
import { handbookPath, searchResultSource } from './labels'

type SearchResultRowProps = {
  result: SearchResultOut
  /** Runs as the link is followed, before the page changes. */
  onNavigate?: () => void
  className?: string
}

/**
 * One handbook search result, from SearchResultRow.jsx: a single link to the section with
 * `?passage=` set, so it opens on the matched passage. The excerpt arrives as segments from the
 * server; each match is a React `<mark>` and the text is never parsed as HTML. The sketch finds
 * the match by searching the excerpt for the query; the API has already marked it. The marker
 * shows, yes or no, on every result. It renders the `li`.
 */
function SearchResultRow({ result, onNavigate, className }: SearchResultRowProps) {
  const { section, passageId, excerpt } = result
  const excerptId = useId()
  const metaId = useId()
  return (
    <li>
      <Link
        to={handbookPath(section.id, passageId)}
        data-slot="search-result-row"
        onClick={onNavigate}
        aria-label={`${section.id} ${section.title}, ${searchResultSource(section)}`}
        aria-describedby={`${excerpt.length > 0 ? `${excerptId} ` : ''}${metaId}`}
        className={cn(
          'grid grid-cols-[72px_minmax(0,1fr)_16px] items-start gap-x-5 border-b border-border-subtle px-3 pt-4 pb-[18px] text-ink no-underline transition-colors hover:bg-primary-tint hover:text-ink max-[760px]:grid-cols-[minmax(0,1fr)_16px]',
          rowFocusRing,
          className,
        )}
      >
        <span className="text-ui leading-6 font-regular text-ink-muted tabular-nums max-[760px]:hidden">
          {section.id}
        </span>
        <span className="flex min-w-0 flex-col gap-1.5">
          <span className="text-body font-semibold">
            {section.title}
            <span className="font-regular text-ink-muted"> · {searchResultSource(section)}</span>
          </span>
          {excerpt.length > 0 && (
            <span
              id={excerptId}
              className="max-w-content truncate text-ui leading-[22px] font-regular text-ink-muted"
            >
              {excerpt.map((segment, index) =>
                segment.match ? (
                  <mark
                    key={index}
                    className="rounded-[3px] bg-primary-tint px-0.5 font-semibold text-ink"
                  >
                    {segment.text}
                  </mark>
                ) : (
                  <Fragment key={index}>{segment.text}</Fragment>
                ),
              )}
            </span>
          )}
          <span id={metaId} className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <ApplicabilityBadge label={section.audienceLabel} />
            <AppliesMarker applies={section.appliesToMe} />
            <LastUpdated date={section.lastUpdated} />
          </span>
        </span>
        <ChevronRight aria-hidden="true" className="mt-1 size-4 text-ink-muted" />
      </Link>
    </li>
  )
}

export { SearchResultRow }
export type { SearchResultRowProps }
