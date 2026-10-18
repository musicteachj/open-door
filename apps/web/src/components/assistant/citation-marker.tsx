import type { CitationOut } from '@/api/generated'
import { cn } from '@/lib/utils'
import { sourceName } from './labels'

type CitationMarkerProps = {
  citation: CitationOut
  /** True while this citation's passage is the one open in the source panel. */
  expanded: boolean
  /** Opens the passage this citation cites. A second press on the open one is the caller's to close. */
  onOpen: (citation: CitationOut) => void
  className?: string
}

/**
 * The small numbered button after a claim (the design's inline marker). It is named by its source
 * ("Source 1: Handbook CA-4.3, California addendum") and says whether its passage is open with
 * `aria-expanded`, which also draws the active state. It sets its own weight and style: the
 * answer's Markdown can put a marker inside bold or italic text, and a marker is not bold or
 * italic. This is what a caller passes `Answer` as `renderMarker`.
 */
function CitationMarker({ citation, expanded, onOpen, className }: CitationMarkerProps) {
  return (
    <button
      data-slot="citation-marker"
      type="button"
      aria-label={sourceName(citation.marker, citation)}
      aria-expanded={expanded}
      onClick={() => onOpen(citation)}
      className={cn(
        'mr-px ml-1 box-border inline-flex h-5 min-w-5 cursor-pointer items-center justify-center rounded-xs border border-border-strong bg-surface-raised px-1.25 align-[1px] text-caption font-semibold text-ink not-italic tabular-nums transition-[background-color,border-color]',
        'hover:border-primary hover:bg-primary-tint',
        'aria-expanded:border-primary aria-expanded:bg-primary-tint',
        className,
      )}
    >
      {citation.marker}
    </button>
  )
}

export { CitationMarker }
export type { CitationMarkerProps }
