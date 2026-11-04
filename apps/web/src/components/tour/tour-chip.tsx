import { ArrowRight, Check } from 'lucide-react'
import { cn } from '@/lib/utils'

type TourChipProps = {
  text: string
  /** After sending: a check and "Sent", muted, `aria-disabled`, still focusable. */
  sent?: boolean
  onSend?: (text: string) => void
  /** Forces the look of a state, for the gallery's static frames (hover or keyboard focus). */
  look?: 'hover' | 'focus'
  className?: string
}

/**
 * A prompt the tour can send as the current persona, in the "Try asking" row style at 44 px with
 * 14 px text and a trailing arrow (from `TourChip` and `.od-tour-chip`). The accessible name is
 * the chip's own text (WCAG 2.5.3, Label in Name); once sent it is "{text}, sent", built from the
 * visible text plus a hidden comma and word, not an `aria-label` that replaces it. A sent chip is
 * `aria-disabled` rather than `disabled`, so keyboard focus is not lost when it is sent, and a
 * press does nothing. The focus ring is inset, so the list's edge does not clip it.
 */
function TourChip({ text, sent = false, onSend, look, className }: TourChipProps) {
  return (
    <button
      type="button"
      data-slot="tour-chip"
      aria-disabled={sent ? true : undefined}
      onClick={() => {
        if (!sent) onSend?.(text)
      }}
      className={cn(
        'flex min-h-11 w-full cursor-pointer items-center justify-between gap-3 border-0 border-b border-border-subtle bg-transparent p-2.5 text-left text-ui leading-5 font-regular text-ink',
        'outline-none focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus-ring focus-visible:outline-solid',
        sent ? 'cursor-default text-ink-muted' : 'hover:bg-primary-tint',
        look === 'hover' && !sent && 'bg-primary-tint',
        look === 'focus' && 'outline-2 -outline-offset-2 outline-focus-ring outline-solid',
        className,
      )}
    >
      {/* One inline wrapper, so the visible text and its hidden suffix are one flex item (no space between). */}
      <span>
        {text}
        {sent && <span className="sr-only">, sent</span>}
      </span>
      {sent ? (
        <>
          <span
            aria-hidden="true"
            className="inline-flex flex-none items-center gap-1 text-small font-semibold text-ink-muted"
          >
            <Check aria-hidden="true" className="size-3.5" strokeWidth={2} />
            Sent
          </span>
        </>
      ) : (
        <ArrowRight aria-hidden="true" className="size-4 shrink-0" />
      )}
    </button>
  )
}

export { TourChip }
export type { TourChipProps }
