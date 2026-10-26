import { BookOpen } from 'lucide-react'
import { useId } from 'react'
import { Link } from 'react-router'
import type { RuleRefOut } from '@/api/generated'
import { cn } from '@/lib/utils'
import { previewCopy, ruleChipLabel, ruleChipName } from './labels'

type RuleChipProps = {
  rule: Pick<RuleRefOut, 'sectionId' | 'title' | 'deepLink'>
  className?: string
}

/**
 * A handbook source as a link chip (the design's `.od-source-chip`): "Handbook §4.1 · Paid time
 * off". A long label truncates with an ellipsis and the link keeps its full name. The title is the
 * API's section title, so an addendum reads "Handbook CA-4.3 · Sick leave" where the design drew
 * the group name ("California addendum").
 */
function RuleChip({ rule, className }: RuleChipProps) {
  return (
    <Link
      data-slot="rule-chip"
      to={rule.deepLink}
      aria-label={ruleChipName(rule)}
      className={cn(
        'box-border inline-flex h-6 max-w-full min-w-0 items-center gap-1.5 rounded-xs border border-border-strong bg-surface-raised px-2 text-caption text-ink tabular-nums no-underline transition-[background-color,border-color]',
        'hover:border-border-strong-hover hover:bg-surface-hover',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus-ring focus-visible:outline-solid',
        className,
      )}
    >
      <BookOpen aria-hidden="true" width={13} height={13} className="flex-none text-ink-muted" />
      <span className="truncate">{ruleChipLabel(rule)}</span>
    </Link>
  )
}

type RuleChipsProps = {
  rules: RuleChipProps['rule'][]
  className?: string
}

/** One rule for each handbook section, in the order first seen: two rules can cite one section. */
function uniqueBySection<T extends Pick<RuleRefOut, 'sectionId'>>(rules: T[]): T[] {
  return rules.filter(
    (rule, index) => rules.findIndex((other) => other.sectionId === rule.sectionId) === index,
  )
}

/** "Sources" and a chip for each rule, wrapping onto more rows as needed. Nothing for no rules. */
function RuleChips({ rules, className }: RuleChipsProps) {
  const labelId = useId()
  if (rules.length === 0) return null
  const shown = uniqueBySection(rules)
  return (
    <div data-slot="rule-chips" className={cn('flex flex-wrap items-center gap-2', className)}>
      <span id={labelId} className="text-caption text-ink-muted">
        {previewCopy.sources}
      </span>
      <ul aria-labelledby={labelId} className="m-0 flex min-w-0 list-none flex-wrap gap-2 p-0">
        {shown.map((rule) => (
          <li key={rule.sectionId} className="flex max-w-full min-w-0">
            <RuleChip rule={rule} />
          </li>
        ))}
      </ul>
    </div>
  )
}

export { RuleChip, RuleChips }
export type { RuleChipProps, RuleChipsProps }
