import { useEffect, useRef, type ReactNode } from 'react'
import { Logo } from '@/components/core/logo'
import { cn } from '@/lib/utils'

type FullPageMessageProps = {
  /** The page's `h1`, and where focus lands when the page appears. */
  title: string
  /** One plain sentence. */
  body?: string
  /** The request ID, shown in Geist Mono and selected with one click. */
  reference?: string
  /** The one way forward: a button or a link. */
  children?: ReactNode
  /** Renders with the logo at the top left, for when there is no shell (a session that is gone). */
  outsideShell?: boolean
  /** Moves focus to the title on mount. On by default; the gallery turns it off. */
  focusOnMount?: boolean
  className?: string
}

/**
 * A calm explanation and one way forward, filling the content sheet (or, outside the shell, the
 * window). From FullPageMessage.jsx. The measure is 440 px, a little narrower than the sketch's
 * 480, so "find it:" doesn't sit alone on a line (the global-states notes ask for this).
 * The title takes focus without a ring: it isn't a control, and a programmatic focus isn't
 * keyboard navigation.
 */
function FullPageMessage({
  title,
  body,
  reference,
  children,
  outsideShell = false,
  focusOnMount = true,
  className,
}: FullPageMessageProps) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    if (focusOnMount) headingRef.current?.focus()
  }, [focusOnMount])

  return (
    <div data-slot="full-page-message" className={cn('flex h-full flex-col', className)}>
      {outsideShell && (
        // The design's frame: a 72 px header inside the landing page's 1168 px column (136 px in
        // from a 1440 px window), with 24 px of padding at the window's edge on a narrow screen.
        <div className="px-6">
          <header className="mx-auto flex h-18 max-w-292 flex-none items-center">
            <Logo />
          </header>
        </div>
      )}
      <div className="flex flex-1 items-center justify-center p-12">
        <div className="-mt-16 flex max-w-110 flex-col items-center gap-3 text-center">
          <h1
            ref={headingRef}
            tabIndex={-1}
            className="m-0 text-h1 text-balance text-ink outline-none"
          >
            {title}
          </h1>
          {body && <p className="m-0 text-body text-pretty text-ink-muted">{body}</p>}
          {reference && (
            <p className="m-0 flex flex-wrap items-center justify-center gap-2 text-small text-ink-muted">
              Reference
              <code className="rounded-xs border border-border bg-surface-sunken px-2 py-0.5 font-mono text-small break-all text-ink select-all">
                {reference}
              </code>
            </p>
          )}
          {children && <div className="mt-3 flex gap-3">{children}</div>}
        </div>
      </div>
    </div>
  )
}

export { FullPageMessage }
export type { FullPageMessageProps }
