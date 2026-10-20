import { cn } from '@/lib/utils'
import type { CrisisSegment } from './crisis-text'
import { APP_LINK } from './link-class'

/** Segments of a fixed text: plain runs, and the links the formatter found. Its words are unchanged. */
function Segments({ segments }: { segments: CrisisSegment[] }) {
  return segments.map((segment, index) =>
    segment.href === undefined ? (
      segment.text
    ) : (
      <a
        key={index}
        href={segment.href}
        {...(segment.external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
        className={cn(APP_LINK, segment.phone && 'whitespace-nowrap tabular-nums')}
      >
        {segment.text}
      </a>
    ),
  )
}

export { Segments }
