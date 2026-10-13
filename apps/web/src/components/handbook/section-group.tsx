import type { ReactNode } from 'react'

type SectionGroupProps = {
  /** The heading's id, which names the group's region. */
  id: string
  /** "4" for a chapter, "CA" for an addendum. */
  num: string
  title: string
  /** "For California employees" on an addendum. */
  note?: string
  /** `SectionRow`s. */
  children?: ReactNode
}

/**
 * A chapter or addendum heading with its rows, from SectionGroup in SectionRow.jsx. The heading
 * is an h2 that names the region; the rows are a list.
 */
function SectionGroup({ id, num, title, note, children }: SectionGroupProps) {
  return (
    <section aria-labelledby={id} className="@container">
      <div className="grid grid-cols-[72px_minmax(0,1fr)] items-baseline gap-x-5 border-b border-border px-3 pt-7 pb-2.5 @max-[56rem]:grid-cols-[3.5rem_minmax(0,1fr)] @max-[56rem]:gap-x-3">
        <span className="text-body font-semibold text-ink-muted tabular-nums">{num}</span>
        <div>
          <h2 id={id} className="inline text-body font-semibold">
            {title}
          </h2>
          {note && (
            <span className="ml-3 text-small font-regular text-ink-muted @max-[56rem]:ml-0 @max-[56rem]:block">
              {note}
            </span>
          )}
        </div>
      </div>
      <ul className="m-0 list-none p-0">{children}</ul>
    </section>
  )
}

export { SectionGroup }
export type { SectionGroupProps }
