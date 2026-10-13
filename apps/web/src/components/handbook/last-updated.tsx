import { formatShortDate } from '@/lib/time'
import { cn } from '@/lib/utils'
import { lastUpdatedText } from './labels'

type LastUpdatedProps = {
  /** The API's ISO calendar date, "2026-09-12". */
  date: string
  /** Only the date, for the section list's column. */
  bare?: boolean
  className?: string
}

/**
 * "Last updated Sep 12, 2026", from LastUpdated.jsx. The sketch takes a date already formatted;
 * this takes the API's ISO date so the format lives in one place.
 */
function LastUpdated({ date, bare = false, className }: LastUpdatedProps) {
  return (
    <span
      className={cn(
        'text-small font-regular whitespace-nowrap text-ink-muted tabular-nums',
        className,
      )}
    >
      {bare ? formatShortDate(date) : lastUpdatedText(date)}
    </span>
  )
}

export { LastUpdated }
export type { LastUpdatedProps }
