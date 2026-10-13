import { useId } from 'react'
import { cn } from '@/lib/utils'
import { handbookCopy } from './labels'

type SourcesBlockProps = {
  /** One line per statutory source, already written out by the server. */
  sources: string[]
  className?: string
}

/**
 * The statutes an addendum was written from (SourcesBlock.jsx). Each line is shown as the
 * handbook states it, with no "Source:" prefix. Renders nothing for a section with no sources.
 */
function SourcesBlock({ sources, className }: SourcesBlockProps) {
  const headingId = useId()
  if (sources.length === 0) return null
  return (
    <section
      aria-labelledby={headingId}
      className={cn('mt-10 flex flex-col gap-1 border-t border-border-subtle pt-4', className)}
    >
      <h2 id={headingId} className="m-0 text-small font-semibold">
        {handbookCopy.sourcesHeading}
      </h2>
      {sources.map((source) => (
        <p key={source} className="m-0 text-small wrap-anywhere text-ink-muted">
          {source}
        </p>
      ))}
    </section>
  )
}

export { SourcesBlock }
export type { SourcesBlockProps }
