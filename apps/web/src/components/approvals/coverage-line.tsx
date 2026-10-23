import { Users } from 'lucide-react'
import type { CoverageOut } from '@/api/generated'
import { cn } from '@/lib/utils'
import { approvalsCopy, coverageLines } from './labels'

type CoverageLineProps = {
  /** Null or missing when the API could not work it out: nothing is shown, never "no one". */
  coverage: CoverageOut[] | null | undefined
  /** The request covers more than one day, so "those days" and not "that day". */
  multiDay: boolean
  /** Muted ink, for a card whose request has moved on. */
  muted?: boolean
  className?: string
}

/**
 * Who else on the team is off (the design's `.od-approval__cov`): the people icon, "Team
 * coverage", then plain text. No color, no warning icon, no ranking: it is context for a person
 * who is deciding, never a verdict.
 */
function CoverageLine({ coverage, multiDay, muted = false, className }: CoverageLineProps) {
  if (!coverage) return null
  return (
    <div data-slot="coverage-line" className={cn('flex items-start gap-2.5', className)}>
      <Users aria-hidden="true" className="mt-0.5 size-4 flex-none text-ink-muted" />
      <div className="flex min-w-0 flex-col">
        <span className="text-small text-ink-muted">{approvalsCopy.teamCoverage}</span>
        {coverageLines(coverage, multiDay).map((line, index) => (
          <span
            // One line per colleague, in order; the "no one" line has no colleague.
            key={coverage[index]?.person.id ?? 'no-one'}
            className={cn(
              'text-ui text-pretty tabular-nums',
              muted ? 'text-ink-muted' : 'text-ink',
            )}
          >
            {line}
          </span>
        ))}
      </div>
    </div>
  )
}

export { CoverageLine }
export type { CoverageLineProps }
