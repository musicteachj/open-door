import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { directoryColumns } from './directory-grid'

// The bar widths of the sketch's four variants, so a column of skeletons doesn't look stamped.
const WIDTHS = [
  ['46%', '62%', '50%', '58%'],
  ['58%', '48%', '40%', '66%'],
  ['40%', '70%', '56%', '52%'],
  ['52%', '56%', '44%', '60%'],
] as const

type SkeletonRowProps = {
  /** Picks one of four width patterns. Any whole number works. */
  variant?: number
  className?: string
}

/**
 * A directory row on its way, from SkeletonRow.jsx. Hidden from screen readers (the table says
 * "Loading the directory" once). Static: the system has no decorative motion, so no shimmer.
 */
function SkeletonRow({ variant = 0, className }: SkeletonRowProps) {
  const n = WIDTHS.length
  const widths = WIDTHS[((Math.trunc(variant) % n) + n) % n]!
  return (
    <div
      data-slot="skeleton-row"
      aria-hidden="true"
      className={cn(directoryColumns, 'h-15 border-b border-border-subtle', className)}
    >
      <span className="flex min-w-0 items-center gap-3">
        <Skeleton className="size-8 flex-none rounded-full" />
        <Skeleton style={{ width: widths[0] }} />
      </span>
      <Skeleton style={{ width: widths[1] }} className="max-[760px]:hidden" />
      <Skeleton style={{ width: widths[2] }} className="max-[760px]:hidden" />
      <Skeleton style={{ width: widths[3] }} className="max-[760px]:hidden" />
      <span />
    </div>
  )
}

export { SkeletonRow }
export type { SkeletonRowProps }
