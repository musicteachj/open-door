import { Info } from 'lucide-react'
import { useId } from 'react'
import type { PtoBalanceOut, RuleRefOut, SickYearOut } from '@/api/generated'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { splitLabel } from './label-parts'
import { balanceCopy } from './labels'
import { RuleChip } from './rule-chip'

type BalanceCardProps =
  | { kind: 'pto'; balance: PtoBalanceOut; rule?: RuleRefOut; className?: string }
  | {
      kind: 'sick'
      year: SickYearOut
      rule?: RuleRefOut
      /** The heading, when it isn't "this year" (next year's grant). */
      label?: string
      className?: string
    }
  | { kind: 'loading'; className?: string }

const cardClass =
  'flex min-w-0 flex-col gap-5 rounded-lg border border-border bg-surface-raised p-6 text-ink'

/** "180 hours" as "180-hour", for "paused at the 180-hour limit". */
function asLimit(hours: string): string {
  return hours.replace(/\s+hours?$/, '-hour')
}

function Ledger({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="m-0 flex flex-col border-t border-border-subtle">
      {rows.map(([term, value]) => (
        <div
          key={term}
          className="flex justify-between gap-4 border-b border-border-subtle py-1.5 text-ui"
        >
          <dt className="text-ink-muted">{term}</dt>
          <dd className="m-0 tabular-nums">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

function Figure({ label, showDays }: { label: string; showDays: boolean }) {
  const { hours, days } = splitLabel(label)
  return (
    <p
      data-slot="balance-figure"
      className="m-0 flex flex-wrap items-baseline gap-x-3 tabular-nums"
    >
      {/* The design's figure is 40/48 semibold; no type token matches it (numeric is 32/40). */}
      <span className="text-[40px]/12 font-semibold tracking-[-0.02em]">{hours}</span>
      {showDays && days && <span className="text-body-lg text-ink-muted">{days}</span>}
    </p>
  )
}

function Head({ id, label, rule }: { id: string; label: string; rule?: RuleRefOut }) {
  return (
    <div className="flex flex-col items-start gap-1.5">
      <h2 id={id} className="m-0 text-body font-semibold">
        {label}
      </h2>
      {rule && <RuleChip rule={rule} />}
    </div>
  )
}

/**
 * A balance card (BalanceCard.jsx): the label with its source chip, the figure (hours large, days
 * beside it), a ledger that adds up to the figure, and footer lines. Every figure is an API label,
 * split at its parenthesis and never worked out here. PTO shows a notice and "Next: paused" when
 * the API says earning is paused (a null next-earning date, which it sends only at the ceiling).
 */
function BalanceCard(props: BalanceCardProps) {
  const headingId = useId()
  if (props.kind === 'loading') {
    return (
      <div
        data-slot="balance-card"
        data-state="loading"
        aria-hidden="true"
        className={cn(cardClass, 'min-h-73', props.className)}
      >
        <Skeleton className="w-30" />
        <Skeleton className="h-8 w-50 rounded-lg" />
        <Skeleton className="w-full" />
        <Skeleton className="w-full" />
        <Skeleton className="w-full" />
        <Skeleton className="w-[70%]" />
      </div>
    )
  }
  if (props.kind === 'sick') {
    const { year, rule, label, className } = props
    return (
      <section
        data-slot="balance-card"
        aria-labelledby={headingId}
        className={cn(cardClass, className)}
      >
        <div className="flex flex-col gap-1">
          <Head id={headingId} label={label ?? balanceCopy.sickLabel} rule={rule} />
          <Figure label={year.availableLabel} showDays={false} />
        </div>
        <Ledger
          rows={[
            [balanceCopy.granted, splitLabel(year.grantedLabel).hours],
            [balanceCopy.used, splitLabel(year.usedLabel).hours],
            [balanceCopy.booked, splitLabel(year.bookedLabel).hours],
          ]}
        />
        <div className="mt-auto flex flex-col gap-0.5 text-small text-ink-muted tabular-nums">
          <p className="m-0">{balanceCopy.renews}</p>
        </div>
      </section>
    )
  }
  const { balance, rule, className } = props
  const paused = balance.nextEarningDate === null
  const ceiling = splitLabel(balance.ceilingLabel).hours
  return (
    <section
      data-slot="balance-card"
      aria-labelledby={headingId}
      className={cn(cardClass, className)}
    >
      <div className="flex flex-col gap-1">
        <Head id={headingId} label={balanceCopy.ptoLabel} rule={rule} />
        <Figure label={balance.availableLabel} showDays />
      </div>
      {paused && (
        <p
          data-slot="balance-notice"
          className="m-0 flex items-start gap-2.5 rounded-md border border-border bg-surface-sunken px-3.5 py-3 text-ui text-pretty"
        >
          <Info aria-hidden="true" className="mt-0.5 size-4 flex-none text-ink-muted" />
          {balanceCopy.pausedNotice(ceiling)}
        </p>
      )}
      <Ledger
        rows={[
          [balanceCopy.earned, splitLabel(balance.earnedLabel).hours],
          [balanceCopy.taken, splitLabel(balance.takenLabel).hours],
          [balanceCopy.booked, splitLabel(balance.bookedLabel).hours],
          [balanceCopy.waiting, splitLabel(balance.pendingLabel).hours],
        ]}
      />
      <div className="mt-auto flex flex-col gap-0.5 text-small text-ink-muted tabular-nums">
        {paused ? (
          <p className="m-0">{balanceCopy.pausedNext(asLimit(ceiling))}</p>
        ) : (
          <>
            <p className="m-0">
              {balanceCopy.next(
                splitLabel(balance.nextEarningLabel).hours,
                balance.nextEarningDate!,
              )}
            </p>
            <p className="m-0">{balanceCopy.canSave(ceiling)}</p>
          </>
        )}
      </div>
    </section>
  )
}

export { BalanceCard }
export type { BalanceCardProps }
