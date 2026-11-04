import { useId } from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

type ConsoleTileProps = {
  title: string
  /** `empty` says "No turns yet"; `loading` keeps the title over static skeleton bars. */
  state?: 'default' | 'empty' | 'loading'
  /** The small line above the figure: "Median". */
  pre?: string
  figure?: string
  lines?: string[]
  /** Term and count pairs, as in "Cards confirmed by a person". */
  rows?: [string, string][]
  /** Sections search came closest with. An empty list says "None yet"; leave it out for no block. */
  closest?: string[]
  /** The sandbox spend line. It stays when the tile is empty. */
  spend?: string
  foot?: string
  className?: string
}

/**
 * One sandbox figure (ConsoleTile.jsx, .od-tile). Always plain ink: a figure above its target is
 * said in words, never styled as a warning. Under 20 turns the foot says "Small sample".
 */
function ConsoleTile({
  title,
  state = 'default',
  pre,
  figure,
  lines = [],
  rows,
  closest,
  spend,
  foot,
  className,
}: ConsoleTileProps) {
  const titleId = useId()
  const line = 'm-0 text-ui font-normal tabular-nums text-pretty'
  return (
    <div
      role="group" // oxlint-disable-line jsx-a11y/prefer-tag-over-role
      aria-labelledby={titleId}
      data-slot="console-tile"
      data-state={state}
      className={cn(
        'flex min-w-0 flex-col rounded-lg border border-border bg-surface-raised px-5 pt-4.5 pb-4 text-ink',
        className,
      )}
    >
      <h3 id={titleId} className="m-0 text-ui font-semibold text-pretty">
        {title}
      </h3>
      {state === 'loading' && (
        <div className="mt-4 flex flex-col gap-2.5">
          <Skeleton className="h-7 w-[45%]" />
          <Skeleton className="w-[80%]" />
          <Skeleton className="w-[56%]" />
        </div>
      )}
      {state === 'empty' && <p className="mt-3 mb-0 text-body text-ink-muted">No turns yet</p>}
      {state === 'default' && figure !== undefined && (
        <p className="mt-2.5 mb-0 flex flex-col">
          {pre && <span className="text-small leading-5 text-ink-muted">{pre}</span>}
          <span className="text-numeric whitespace-nowrap tabular-nums">{figure}</span>
        </p>
      )}
      {state === 'default' &&
        lines.map((text) => (
          <p key={text} className={line}>
            {text}
          </p>
        ))}
      {state === 'default' && rows && (
        <dl className="mt-2.5 mb-0 p-0">
          {rows.map(([term, count]) => (
            <div
              key={term}
              className="flex justify-between gap-3 border-t border-border-subtle py-1.5 text-ui leading-5 font-normal"
            >
              <dt>{term}</dt>
              <dd className="m-0 font-semibold tabular-nums">{count}</dd>
            </div>
          ))}
        </dl>
      )}
      {state === 'default' && closest && (
        <p className="mt-2.5 mb-0 flex flex-col">
          <span className="text-small leading-5 font-normal text-ink-muted">
            Search came closest with:
          </span>
          {closest.length === 0 ? (
            <span className="text-ui leading-5 font-normal">None yet</span>
          ) : (
            closest.map((text) => (
              <span key={text} className="text-ui leading-5 font-normal tabular-nums">
                {text}
              </span>
            ))
          )}
        </p>
      )}
      {state !== 'loading' && spend && <p className={cn(line, 'mt-2.5')}>{spend}</p>}
      <div className="min-h-3 flex-1" />
      {state === 'default' && foot && (
        <p className="m-0 border-t border-border-subtle pt-2.5 text-small text-ink-muted tabular-nums">
          {foot}
        </p>
      )}
    </div>
  )
}

export { ConsoleTile }
export type { ConsoleTileProps }
