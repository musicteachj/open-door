import { useId } from 'react'
import { formatShortDate } from '@/lib/time'
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
// The handbook files keep each source's full address and ISO date, so a reader can check it. The
// page shows the shorter form the design uses: "read from dir.ca.gov on Oct 7, 2026."
const WEB_ADDRESS = /https?:\/\/(?:www\.)?([^/\s]+)\S*?(?=[.,;:)]?(?:\s|$))/g
const ISO_DATE = /\b(\d{4}-\d{2}-\d{2})\b/g

function sourceForDisplay(source: string): string {
  return source
    .replace(WEB_ADDRESS, (_match, site: string) => site)
    .replace(ISO_DATE, (_match, date: string) => formatShortDate(date))
}

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
          {sourceForDisplay(source)}
        </p>
      ))}
    </section>
  )
}

export { SourcesBlock }
export type { SourcesBlockProps }
