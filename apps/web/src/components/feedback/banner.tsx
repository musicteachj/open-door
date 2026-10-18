import { TriangleAlert, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

type BannerProps = {
  /**
   * Plain text, or text with a few links in it. It is rendered inside a `<p>`, so it must be
   * phrasing content: text and inline elements only, never a block, a list, or a paragraph.
   */
  message: ReactNode
  /**
   * An action beside the message, such as "Start a new sandbox". With one, the banner wraps, so
   * on a narrow screen the action drops under the text.
   */
  action?: ReactNode
  /** Shows a close button. Leave it out for a banner that can't be closed. */
  onDismiss?: () => void
  /** The close button's name. It says the scope, for screen readers. From Banner.jsx. */
  dismissLabel?: string
  /**
   * A polite status by default. Pass false when a banner's text changes while it is shown (a
   * countdown) and something else announces it once: a live region would announce every change.
   */
  live?: boolean
  className?: string
}

/**
 * Flags something about the whole session, such as the sandbox about to reset. From Banner.jsx.
 * A polite status (`<output>`, which oxlint's jsx-a11y rule asks for over `role="status"`), so it
 * never interrupts a screen reader. The warning color is paired with its icon and ink text.
 */
function Banner({
  message,
  action,
  onDismiss,
  dismissLabel = 'Dismiss for this session',
  live = true,
  className,
}: BannerProps) {
  const Root = live ? 'output' : 'div'
  return (
    <Root
      data-slot="banner"
      className={cn(
        'flex items-center gap-3 border-b border-border bg-surface-sunken py-2.5 pr-3 pl-5',
        action && 'flex-wrap',
        className,
      )}
    >
      <TriangleAlert
        data-slot="banner-icon"
        aria-hidden="true"
        className="size-4.5 shrink-0 text-warning"
      />
      <p className={cn('m-0 flex-1 text-ui text-ink', action && 'min-w-48')}>{message}</p>
      {action}
      {onDismiss && (
        <button
          type="button"
          aria-label={dismissLabel}
          onClick={onDismiss}
          className="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-sm text-ink-muted hover:bg-neutral-hover hover:text-ink"
        >
          <X aria-hidden="true" className="size-4" />
        </button>
      )}
    </Root>
  )
}

export { Banner }
export type { BannerProps }
