import { ShieldCheck } from 'lucide-react'
import { EmptyCell } from '@/components/core/empty-cell'
import { cn } from '@/lib/utils'
import { formatDuration as formatMs } from './labels'

/**
 * The quiet neutral tag for a possible prompt injection (.od-inj-tag). Never an alert. Stacked, it
 * breaks onto two lines for the narrow column beside a docked trace.
 */
function InjectionTag({ stacked = false }: { stacked?: boolean }) {
  return (
    <span
      data-slot="injection-tag"
      className={cn(
        'inline-flex gap-x-1 rounded-xs border border-border-strong bg-surface-sunken px-1.5 py-px text-caption leading-[18px] whitespace-nowrap text-ink-muted',
        stacked && 'flex-col',
      )}
    >
      <span>Possible prompt</span> <span>injection</span>
    </span>
  )
}

/** "ordinary" as "Ordinary". The console only keeps ordinary turns as timed rows. */
function categoryWord(category: string): string {
  return category.charAt(0).toUpperCase() + category.slice(1)
}

type SafetyLabelProps = {
  /** The guard's category, or null when the turn wasn't screened. */
  category: string | null
  /** The safety check's time, for the trace. The table leaves it out. */
  ms?: number | null
  injection?: boolean | null
  stacked?: boolean
}

/** The safety check's verdict with the injection tag beneath it when set (SafetyLabel). */
function SafetyLabel({ category, ms, injection = false, stacked = false }: SafetyLabelProps) {
  if (category === null) {
    return <EmptyCell />
  }
  return (
    <span className="flex min-w-0 flex-col items-start gap-1">
      <span className="inline-flex items-center gap-2 text-ui font-normal">
        <ShieldCheck aria-hidden="true" className="size-4 shrink-0 text-ink-muted" />
        {categoryWord(category)}
        {ms != null && <span className="whitespace-nowrap text-ink-muted">· {formatMs(ms)}</span>}
      </span>
      {injection && <InjectionTag stacked={stacked} />}
    </span>
  )
}

export { InjectionTag, SafetyLabel }
export type { SafetyLabelProps }
