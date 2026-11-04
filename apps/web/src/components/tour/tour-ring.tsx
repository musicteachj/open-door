import { cn } from '@/lib/utils'
import type { Rect } from './place-coach-mark'

type TourRingProps = {
  /** The target's rectangle in viewport coordinates, or null when it is missing. */
  rect: Rect | null
  /** The target's own corner radius in px; the ring's is this plus the 4 px it sits outside. */
  radius?: number
  /** `fixed` (the default) for viewport coordinates; `absolute` for a rectangle inside a positioned box. */
  position?: 'fixed' | 'absolute'
}

/**
 * The 2 px primary ring around a tour target, drawn 4 px outside it (from `TourRing` and
 * `.od-tour-ring` in the design). Never an overlay, a spotlight, or dimming. It takes no clicks,
 * and it sits above the page but below the coach mark. The ring is never the only signal: the
 * coach mark's text names the target.
 */
function TourRing({ rect, radius = 8, position = 'fixed' }: TourRingProps) {
  if (rect === null) return null
  return (
    <div
      data-slot="tour-ring"
      aria-hidden="true"
      className={cn(
        'pointer-events-none z-24 box-border outline-2 outline-primary',
        position === 'fixed' ? 'fixed' : 'absolute',
      )}
      style={{
        left: rect.x - 4,
        top: rect.y - 4,
        width: rect.width + 8,
        height: rect.height + 8,
        borderRadius: radius + 4,
      }}
    />
  )
}

export { TourRing }
export type { TourRingProps }
