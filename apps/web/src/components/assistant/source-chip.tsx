import { useId } from 'react'
import type { CitationOut } from '@/api/generated'
import { cn } from '@/lib/utils'
import { chipLabel, conversationCopy, sourceName } from './labels'
import { firstPerSection } from './sources'

type SourceChipProps = {
  citation: CitationOut
  /** True while this chip's passage is the one open in the source panel. */
  expanded: boolean
  onOpen: (citation: CitationOut) => void
  className?: string
}

/**
 * A source under the answer: the marker number in a badge, then "Handbook CA-4.3 · California
 * addendum". The label truncates with an ellipsis when the row is narrow, and the button's name
 * keeps the full source, the same as its marker's.
 */
function SourceChip({ citation, expanded, onOpen, className }: SourceChipProps) {
  return (
    <button
      data-slot="source-chip"
      data-passage-id={citation.passageId}
      type="button"
      aria-label={sourceName(citation.marker, citation)}
      aria-expanded={expanded}
      onClick={() => onOpen(citation)}
      className={cn(
        'box-border inline-flex h-8 max-w-full min-w-0 cursor-pointer items-center gap-2 rounded-sm border border-border-strong bg-surface-raised pr-3 pl-1.5 text-small text-ink transition-[background-color,border-color]',
        'hover:border-primary hover:bg-primary-tint',
        'aria-expanded:border-primary aria-expanded:bg-primary-tint',
        className,
      )}
    >
      <span
        aria-hidden="true"
        className="box-border inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-xs border border-border-strong bg-surface-raised px-1.25 text-caption font-semibold tabular-nums"
      >
        {citation.marker}
      </span>
      <span className="truncate">{chipLabel(citation)}</span>
    </button>
  )
}

type SourceChipsProps = {
  /**
   * Every citation of the answer, already numbered by section (`numberBySection`). The chips are
   * the distinct sections among them.
   */
  citations: CitationOut[]
  /** The passage open in the source panel, if any. */
  openPassageId?: string | null
  onOpen: (citation: CitationOut) => void
  className?: string
}

/** The "Sources" label and the chips, wrapping onto more rows as needed. */
function SourceChips({ citations, openPassageId = null, onOpen, className }: SourceChipsProps) {
  const labelId = useId()
  const sources = firstPerSection(citations)
  if (sources.length === 0) return null
  return (
    <div data-slot="source-chips" className={cn('mt-0.5 flex flex-col gap-2', className)}>
      <p id={labelId} className="m-0 text-small text-ink-muted">
        {conversationCopy.sources}
      </p>
      <ul aria-labelledby={labelId} className="m-0 flex list-none flex-wrap gap-2 p-0">
        {sources.map((citation) => {
          const open = citations.find(
            (cited) => cited.sectionId === citation.sectionId && cited.passageId === openPassageId,
          )
          return (
            <li key={citation.marker} className="flex max-w-full min-w-0">
              <SourceChip
                citation={citation}
                expanded={open !== undefined}
                // An open chip hands back the passage that is open in its section, not its own first
                // one, so the caller's "the same passage again closes it" rule closes the panel.
                onOpen={() => onOpen(open ?? citation)}
              />
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export { SourceChip, SourceChips }
export type { SourceChipProps, SourceChipsProps }
