import { useEffect, useId, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { useMediaQuery } from '@/hooks/use-media-query'
import { cn } from '@/lib/utils'
import { PHONE_MAX_WIDTH } from './place-coach-mark'
import { useTourEscape } from './use-tour-escape'

type TourEndCardProps = {
  /** The persona's first name, for "Keep exploring as Dana". */
  persona: string
  onKeepExploring: () => void
  /** Escape ends the tour like every other step. Without it, Escape keeps exploring. */
  onLeave?: () => void
  onChoose: () => void
  /** Moves focus to the heading on mount. Off for the gallery's frame. */
  focusOnMount?: boolean
  /** Draws in normal flow instead of centered over the window, for the gallery. */
  inFlow?: boolean
  className?: string
}

/**
 * The tour's last step (screen 15, from `TourEndCard` and `.od-tour-end`): a 520 px card centered
 * over the content, a non-modal dialog named by its heading. No scrim, no dimming, no
 * celebration; the page behind stays visible. At 640 px and below it docks to the bottom as a
 * sheet like the coach mark. Focus goes to the heading on mount; the heading carries a hidden
 * "Step 10 of 10: " and the visible count is `aria-hidden`.
 */
function TourEndCard({
  persona,
  onKeepExploring,
  onLeave,
  onChoose,
  focusOnMount = true,
  inFlow = false,
  className,
}: TourEndCardProps) {
  const titleId = useId()
  const titleRef = useRef<HTMLHeadingElement>(null)
  // In flow (the gallery), it stays where it is, so it never covers the page it is shown on.
  const phone = useMediaQuery(`(max-width: ${PHONE_MAX_WIDTH}px)`) && !inFlow
  useTourEscape(onLeave ?? onKeepExploring, !inFlow)
  useEffect(() => {
    if (focusOnMount) titleRef.current?.focus()
  }, [focusOnMount])

  return (
    <div
      // A non-modal dialog that sits in the page, not a native <dialog> (which is top-layer and modal-like).
      // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role
      role="dialog"
      aria-modal="false"
      aria-labelledby={titleId}
      data-slot="tour-end-card"
      data-tour-own=""
      className={cn(
        'z-25 box-border flex flex-col gap-3 border border-border-strong bg-surface-raised pt-6 pr-7 pb-7 pl-7 text-ink shadow-md',
        phone
          ? 'fixed inset-x-0 bottom-0 w-auto rounded-t-xl pb-[calc(28px+env(safe-area-inset-bottom))]'
          : 'w-130 max-w-[calc(100%-32px)] rounded-xl',
        !phone && !inFlow && 'fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2',
        className,
      )}
    >
      <span aria-hidden="true" className="text-caption text-ink-muted tabular-nums">
        Step 10 of 10
      </span>
      <h2
        id={titleId}
        ref={titleRef}
        tabIndex={-1}
        className="m-0 text-h2 font-semibold outline-none"
      >
        <span className="sr-only">{'Step 10 of 10: '}</span>
        That’s the tour
      </h2>
      <p className="m-0 text-body text-pretty">
        You’ve seen answers that change by state and always cite the handbook, a day off requested
        and approved on cards a person confirmed, private details kept private, a sensitive concern
        sent to HR in the person’s own words, and a record of everything the AI did.
      </p>
      <p className="m-0 text-body text-pretty text-ink-muted">
        This sandbox stays for 24 hours, so keep exploring.
      </p>
      <div className="mt-2 flex flex-wrap gap-3">
        <Button className="transition-none" onClick={onKeepExploring}>
          Keep exploring as {persona}
        </Button>
        <Button variant="secondary" className="transition-none" onClick={onChoose}>
          Choose who to be
        </Button>
      </div>
    </div>
  )
}

export { TourEndCard }
export type { TourEndCardProps }
