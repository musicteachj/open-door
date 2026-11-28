import { LoaderCircle } from 'lucide-react'
import { type ReactNode, useEffect, useState } from 'react'
import { cn } from '@/lib/utils'

/** A load quicker than this shows nothing, so a fast page never flashes a loader. */
export const PAGE_LOADING_DELAY_MS = 300

type PageLoadingProps = {
  /** What a screen reader hears, and what the visible line says. */
  text?: string
  /** What to show once the delay has passed. The spinner line by default. */
  children?: ReactNode
  className?: string
}

/**
 * What a page shows while it waits for its first data (ADR 0025). A screen reader hears the
 * status at once, as before. After a short delay a quiet loader fades in where the page will be,
 * so a slow load is never a blank screen. The visible part is hidden from assistive technology,
 * because the status already says it.
 */
function PageLoading({ text = 'Loading…', children, className }: PageLoadingProps) {
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), PAGE_LOADING_DELAY_MS)
    return () => clearTimeout(timer)
  }, [])
  return (
    <div data-slot="page-loading" className={className}>
      <output className="sr-only">{text}</output>
      {visible && (
        <div aria-hidden="true" className="motion-safe:animate-fade-in">
          {children ?? <LoadingLine text={text} />}
        </div>
      )}
    </div>
  )
}

/** A spinner and the loading words in muted ink, centered in the window. */
function LoadingLine({ text, className }: { text: string; className?: string }) {
  return (
    <div className={cn('flex min-h-dvh items-center justify-center', className)}>
      <span className="flex items-center gap-2 text-ui text-ink-muted">
        <LoaderCircle className="size-4 shrink-0 animate-spin text-primary" />
        {text}
      </span>
    </div>
  )
}

export { PageLoading }
