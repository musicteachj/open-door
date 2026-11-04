import { CirclePlay, RotateCcw } from 'lucide-react'
import { DropdownMenuItem } from '@/components/ui/dropdown-menu'

type TourMenuItemsProps = {
  /** The step the visitor is on, when a tour is in progress. Leave out when idle. */
  step?: number
  total?: number
  onTake: () => void
  onResume: () => void
  onRestart: () => void
}

/**
 * The tour's rows in the persona menu (PersonaMenu's `extra` slot, from `TourMenuItems`). Idle:
 * "Take the tour". In progress: "Resume the tour" with the step under it, and "Start the tour
 * over". Resume's name is its visible text plus a hidden comma ("Resume the tour, Step 5 of 10"),
 * not an `aria-label` that replaces it, so it starts with what it shows (WCAG 2.5.3).
 */
function TourMenuItems({ step, total = 10, onTake, onResume, onRestart }: TourMenuItemsProps) {
  if (step === undefined) {
    return (
      <DropdownMenuItem onSelect={onTake}>
        <CirclePlay aria-hidden="true" className="size-4 text-ink-muted" />
        Take the tour
      </DropdownMenuItem>
    )
  }
  return (
    <>
      <DropdownMenuItem onSelect={onResume} className="py-2">
        <CirclePlay aria-hidden="true" className="size-4 text-ink-muted" />
        <span className="flex flex-col">
          {/* The hidden comma ends the first line, inside its span, so no space comes before it. */}
          <span>
            Resume the tour
            <span className="sr-only">,</span>
          </span>
          <span className="text-caption leading-4 text-ink-muted tabular-nums">
            Step {step} of {total}
          </span>
        </span>
      </DropdownMenuItem>
      <DropdownMenuItem onSelect={onRestart}>
        <RotateCcw aria-hidden="true" className="size-4 text-ink-muted" />
        Start the tour over
      </DropdownMenuItem>
    </>
  )
}

export { TourMenuItems }
export type { TourMenuItemsProps }
