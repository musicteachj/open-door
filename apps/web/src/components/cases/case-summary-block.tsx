import { RotateCcw } from 'lucide-react'
import { useId } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { Skeleton } from '@/components/ui/skeleton'
import { AiTag } from './ai-tag'
import { dateTimeInZone, modelDisplayName } from './case-dates'
import { detailCopy } from './labels'
import type { SummaryState } from './summary-state'

type CaseSummaryBlockProps = {
  state: SummaryState
  /** The summary, for `written`. Shown as plain text: never Markdown, never a link. */
  text?: string
  /** When it was written (a UTC timestamp), for `written`. */
  writtenAt?: string
  /** The model's id, for `written`. Shown as its display name when it is known. */
  model?: string
  /** The viewer's location's time zone. */
  timeZone?: string
  /** "Try again", for `failed`. */
  onRetry?: () => void
  /** "Try again" is offered. Off for a closed case: the server writes no new summary for one. */
  canRetry?: boolean
  /** A retry is in flight: the button is busy and does nothing. */
  retrying?: boolean
  className?: string
}

/**
 * The AI's summary of a case, always labeled as the AI's (CaseSummaryBlock.jsx). A section named
 * "AI summary": busy while pending, with "Writing the summary…" as a status and three static bars.
 * The text is plain: it was written from the person's words and is shown as text with its line
 * breaks, with no Markdown and no links. A crisis case has none.
 */
function CaseSummaryBlock({
  state,
  text,
  writtenAt,
  model,
  timeZone = 'UTC',
  onRetry,
  canRetry = true,
  retrying = false,
  className,
}: CaseSummaryBlockProps) {
  const headingId = useId()
  return (
    <section
      data-slot="case-summary"
      aria-labelledby={headingId}
      aria-busy={state === 'pending' || undefined}
      className={cn('overflow-hidden rounded-lg border border-border', className)}
    >
      <div className="flex flex-col gap-0.5 border-b border-border-subtle bg-surface-sunken px-5 py-3">
        <div className="flex items-center gap-2">
          <AiTag />
          <h2 id={headingId} className="m-0 text-body font-semibold">
            {detailCopy.summaryTitle}
          </h2>
        </div>
        {state === 'written' && (
          <p className="m-0 text-small text-ink-muted tabular-nums">
            {detailCopy.summaryMeta}
            {writtenAt && ` · ${dateTimeInZone(writtenAt, timeZone)}`}
            {model && (
              <>
                {' · '}
                <span className="whitespace-nowrap">{modelDisplayName(model)}</span>
              </>
            )}
          </p>
        )}
      </div>
      <div className="px-5 pt-4 pb-4.5 text-body">
        {state === 'written' && (
          <p className="m-0 text-[16px]/6.5 text-pretty whitespace-pre-wrap">{text}</p>
        )}
        {state === 'pending' && (
          <output className="block">
            <span className="block text-ink-muted">{detailCopy.summaryPending}</span>
            <span aria-hidden="true" className="mt-3 flex flex-col gap-2.5">
              <Skeleton className="w-[92%] rounded-[6px]" />
              <Skeleton className="w-[78%] rounded-[6px]" />
              <Skeleton className="w-[54%] rounded-[6px]" />
            </span>
          </output>
        )}
        {state === 'failed' && (
          <div className="flex flex-wrap items-center gap-4">
            <p className="m-0 min-w-60 flex-1">{detailCopy.summaryFailed}</p>
            {canRetry && (
              <Button variant="secondary" size="sm" loading={retrying} onClick={onRetry}>
                {!retrying && <RotateCcw aria-hidden="true" className="size-3.5" />}
                {detailCopy.tryAgain}
              </Button>
            )}
          </div>
        )}
        {state === 'crisis' && <p className="m-0">{detailCopy.summaryCrisis}</p>}
      </div>
    </section>
  )
}

export { CaseSummaryBlock }
export type { CaseSummaryBlockProps }
