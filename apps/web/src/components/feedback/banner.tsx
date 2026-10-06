import { TriangleAlert, X } from 'lucide-react'
import { cn } from '@/lib/utils'

type BannerProps = {
  message: string
  /** Shows a close button. Leave it out for a banner that can't be closed. */
  onDismiss?: () => void
  /** The close button's name. It says the scope, for screen readers. From Banner.jsx. */
  dismissLabel?: string
  className?: string
}

/**
 * Flags something about the whole session, such as the sandbox about to reset. From Banner.jsx.
 * A polite status (`<output>`, which oxlint's jsx-a11y rule asks for over `role="status"`), so it
 * never interrupts a screen reader. The warning color is paired with its icon and ink text.
 */
function Banner({
  message,
  onDismiss,
  dismissLabel = 'Dismiss for this session',
  className,
}: BannerProps) {
  return (
    <output
      data-slot="banner"
      className={cn(
        'flex items-center gap-3 border-b border-border bg-surface-sunken py-2.5 pr-3 pl-5',
        className,
      )}
    >
      <TriangleAlert
        data-slot="banner-icon"
        aria-hidden="true"
        className="size-4.5 shrink-0 text-warning"
      />
      <p className="m-0 flex-1 text-ui text-ink">{message}</p>
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
    </output>
  )
}

export { Banner }
export type { BannerProps }
