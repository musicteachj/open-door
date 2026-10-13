import { Link } from 'react-router'
import type { SectionSummary } from '@/api/generated'
import { rowFocusRing } from '@/components/ui/focus-ring'
import { cn } from '@/lib/utils'
import { chapterNavHeading, handbookPath } from './labels'

type ChapterNavProps = {
  /** The section being read; its chapter or addendum names the navigator and it is the current link. */
  section: SectionSummary
  /** That chapter's (or addendum's) sections, in handbook order. */
  sections: SectionSummary[]
  className?: string
}

/**
 * The slim chapter navigator beside a section page (.od-sec-nav in the sketch's CSS, which has no
 * component of its own). The current section is tinted and carries `aria-current="page"`. Plain
 * links in the Tab order; no arrow-key handling.
 */
function ChapterNav({ section, sections, className }: ChapterNavProps) {
  const heading = chapterNavHeading(section)
  return (
    <nav aria-label={heading} className={className}>
      <p className="mb-2 px-2.5 text-small font-semibold text-ink-muted">{heading}</p>
      <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
        {sections.map((item) => {
          const current = item.id === section.id
          return (
            <li key={item.id}>
              <Link
                to={handbookPath(item.id)}
                aria-current={current ? 'page' : undefined}
                className={cn(
                  'grid grid-cols-[52px_minmax(0,1fr)] items-baseline rounded-md px-2.5 py-1.5 text-ui font-regular text-ink no-underline hover:bg-neutral-hover hover:text-ink',
                  rowFocusRing,
                  current && 'bg-primary-tint font-semibold hover:bg-primary-tint',
                )}
              >
                <span className="font-regular text-ink-muted tabular-nums">{item.id}</span>{' '}
                <span>{item.title}</span>
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

export { ChapterNav }
export type { ChapterNavProps }
