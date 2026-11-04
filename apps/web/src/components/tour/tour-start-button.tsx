import { CirclePlay } from 'lucide-react'
import { Button } from '@/components/ui/button'

type TourStartButtonProps = {
  /** A new sandbox is starting: busy, a spinner, and a polite status line. */
  starting?: boolean
  /** Who the tour starts as, for the status line. */
  persona?: string
  onStart: () => void
}

/**
 * The landing's "Take the 2-minute tour" (from the Landing tour button in the design). While it
 * starts, the button shows a spinner and "Starting the tour…", is `aria-busy`, and ignores presses
 * (the shared `Button`'s loading state keeps it focusable instead of disabling it), and a polite
 * status line announces "Starting the tour as Priya Raman." The status region is always in the
 * page, so the text is announced when it appears.
 */
function TourStartButton({
  starting = false,
  persona = 'Priya Raman',
  onStart,
}: TourStartButtonProps) {
  return (
    <>
      <Button variant="secondary" loading={starting} onClick={onStart}>
        {!starting && <CirclePlay aria-hidden="true" className="size-4 text-ink-muted" />}
        {starting ? 'Starting the tour…' : 'Take the 2-minute tour'}
      </Button>
      <output className="sr-only">{starting ? `Starting the tour as ${persona}.` : ''}</output>
    </>
  )
}

export { TourStartButton }
export type { TourStartButtonProps }
