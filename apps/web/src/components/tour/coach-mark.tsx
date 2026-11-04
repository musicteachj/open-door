import { X } from 'lucide-react'
import { useEffect, useId, useRef, type CSSProperties, type Ref } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { Placement } from './place-coach-mark'
import { TourChip } from './tour-chip'
import { useTourEscape } from './use-tour-escape'

type CoachMarkProps = {
  /** 1-based. A change moves focus to the title. */
  step: number
  total?: number
  title: string
  body: string
  /** What would have appeared, when the step's expected result did not. A polite status. */
  missing?: string
  chips?: readonly string[]
  /** Indexes of the chips already sent. */
  sent?: readonly number[]
  /** The step's result has appeared: Next replaces Skip this step. */
  resultShown?: boolean
  /** From `placeCoachMark`. */
  placement: Placement
  onBack?: () => void
  onNext?: () => void
  onSkip?: () => void
  onLeave: () => void
  onSend?: (index: number) => void
  /** Moves focus to the title on mount and when the step changes. Off for the gallery's frames. */
  focusOnStep?: boolean
  /** Draws in normal flow instead of fixed to the window, for the gallery. */
  inFlow?: boolean
  className?: string
  /** The card's element, so the host can measure it. */
  cardRef?: Ref<HTMLDivElement>
}

/**
 * One step of the guided tour (screen 15, from `CoachMark` and `.od-coach`): a non-modal dialog
 * (`aria-modal="false"`, the page stays usable) labeled by its title. The title carries a visually
 * hidden "Step N of 10: " so the step is announced with it, and the visible count is
 * `aria-hidden` so it is not read twice. Focus moves to the title (`tabIndex=-1`) on mount and
 * whenever the step changes, and nowhere else, so a move of the card never steals it.
 *
 * Escape leaves the tour from anywhere on the page, unless a menu or dialog is open (Radix closes
 * that first). Sent chips, the missing line, and the footer follow the notes: Back is hidden on
 * step 1; "Skip this step" shows until the result appears, then Next, and a step without chips has
 * Next from the start. There are no transitions or animations at all, so reduced motion needs no
 * special case.
 *
 * On a phone (`placement.mode === 'sheet'`) it docks to the bottom, full width, top corners
 * rounded, with the safe area below the buttons and no pointer. Elsewhere it sits at the
 * placement's viewport coordinates, with a 12 px rotated-square pointer on the edge facing the
 * target (none when centered).
 */
function CoachMark({
  step,
  total = 10,
  title,
  body,
  missing,
  chips = [],
  sent = [],
  resultShown = false,
  placement,
  onBack,
  onNext,
  onSkip,
  onLeave,
  onSend,
  focusOnStep = true,
  inFlow = false,
  className,
  cardRef,
}: CoachMarkProps) {
  const titleId = useId()
  const titleRef = useRef<HTMLHeadingElement>(null)
  // A card drawn in flow (the gallery) is a picture of one, not the tour: it must not take Escape
  // from the page's own panels.
  useTourEscape(onLeave, !inFlow)

  useEffect(() => {
    if (focusOnStep) titleRef.current?.focus()
  }, [step, focusOnStep])

  const done = resultShown || chips.length === 0
  const stepText = `Step ${step} of ${total}`
  const sheet = placement.mode === 'sheet'
  const style: CSSProperties | undefined =
    inFlow || sheet ? undefined : { position: 'fixed', left: placement.x, top: placement.y }

  return (
    <div
      // A non-modal dialog that sits in the page, not a native <dialog> (which is top-layer and modal-like).
      // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role
      role="dialog"
      aria-modal="false"
      aria-labelledby={titleId}
      ref={cardRef}
      data-slot="coach-mark"
      data-tour-own=""
      style={style}
      className={cn(
        'z-25 box-border flex flex-col gap-2 border border-border-strong bg-surface-raised py-3 pr-3 pb-4 pl-5 text-ink shadow-md',
        sheet
          ? 'fixed inset-x-0 bottom-0 w-auto rounded-t-xl pb-[calc(16px+env(safe-area-inset-bottom))]'
          : 'w-90 max-w-full rounded-lg',
        inFlow && 'relative',
        className,
      )}
    >
      {placement.mode === 'anchored' && (
        <span
          data-slot="coach-mark-pointer"
          data-side={placement.side}
          aria-hidden="true"
          style={
            placement.side === 'right'
              ? { top: placement.pointerOffset - 6 }
              : { left: placement.pointerOffset - 6 }
          }
          className={cn(
            'absolute size-3 rotate-45 bg-surface-raised',
            placement.side === 'bottom' && '-top-[7px] border-t border-l border-border-strong',
            placement.side === 'top' && '-bottom-[7px] border-r border-b border-border-strong',
            placement.side === 'right' && '-left-[7px] border-b border-l border-border-strong',
          )}
        />
      )}
      <div className="flex items-center justify-between gap-3">
        <span aria-hidden="true" className="text-caption text-ink-muted tabular-nums">
          {stepText}
        </span>
        <button
          type="button"
          aria-label="Leave the tour"
          onClick={onLeave}
          className="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-sm text-ink-muted hover:bg-neutral-hover hover:text-ink"
        >
          <X aria-hidden="true" className="size-4" />
        </button>
      </div>
      <h2
        id={titleId}
        ref={titleRef}
        tabIndex={-1}
        className="m-0 -mt-1.5 mr-2 text-[17px]/6 font-semibold text-pretty outline-none"
      >
        <span className="sr-only">{`${stepText}: `}</span>
        {title}
      </h2>
      <p className="m-0 mr-2 text-ui leading-[22px] font-regular text-pretty">{body}</p>
      {missing !== undefined && (
        // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role
        <p role="status" className="m-0 mr-2 text-small text-pretty text-ink-muted">
          {missing}
        </p>
      )}
      {chips.length > 0 && (
        <div className="mt-1 mr-2 flex flex-col border-t border-border-subtle">
          {chips.map((text, index) => (
            <TourChip
              key={`${index}-${text}`}
              text={text}
              sent={sent.includes(index)}
              onSend={() => onSend?.(index)}
            />
          ))}
        </div>
      )}
      <div className="mt-2 mr-2 flex items-center gap-2">
        {step > 1 && (
          <Button variant="secondary" size="sm" className="transition-none" onClick={onBack}>
            Back
          </Button>
        )}
        <span className="flex-1" />
        {done ? (
          <Button size="sm" className="transition-none" onClick={onNext}>
            Next
          </Button>
        ) : (
          <Button variant="ghost" size="sm" className="transition-none" onClick={onSkip}>
            Skip this step
          </Button>
        )}
      </div>
    </div>
  )
}

export { CoachMark }
export type { CoachMarkProps }
