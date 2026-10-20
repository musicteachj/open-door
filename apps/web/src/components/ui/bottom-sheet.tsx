import { Dialog as DialogPrimitive } from 'radix-ui'
import { useRef, useState, type PointerEvent, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

/** How far down the handle has to be dragged, in pixels, before letting go closes the sheet. */
const DISMISS_DRAG_PX = 80

/** The sheet's visible title. The dialog is named by it, so the sheet's content must hold one. */
const SheetTitle = DialogPrimitive.Title

type BottomSheetProps = {
  /** Called for Escape, a press on the overlay, and a swipe down on the handle. */
  onClose: () => void
  children: ReactNode
  className?: string
}

/**
 * A modal sheet that rises from the bottom and covers the page: Radix Dialog, so focus stays
 * inside, the page behind it is hidden from assistive technology and can't be pressed, and Escape
 * closes it. It is always open while it is mounted: the page mounts it for as long as it should
 * show. Closing is the page's to do, since the page owns what keeps it open (the URL). Focus
 * returning to what opened it is the page's too, so the dialog's own return is turned off.
 *
 * The handle at the top, and any `<header>` in the content, are the swipe-down targets: drag past
 * 80 px and let go to close. A control in the header does not start a drag, and the body never
 * does, so it scrolls as normal. The content must hold a `SheetTitle`, which names the dialog.
 */
function BottomSheet({ onClose, children, className }: BottomSheetProps) {
  const drag = useRef<{ startY: number; pointerId: number } | null>(null)
  const [offset, setOffset] = useState(0)
  const [dragging, setDragging] = useState(false)

  function startDrag(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return
    const target = event.target instanceof Element ? event.target : null
    if (target === null || target.closest('button, a, input, textarea, select')) return
    if (!target.closest('[data-slot="bottom-sheet-handle"], header')) return
    drag.current = { startY: event.clientY, pointerId: event.pointerId }
    event.currentTarget.setPointerCapture(event.pointerId)
    setDragging(true)
  }
  function moveDrag(event: PointerEvent<HTMLDivElement>) {
    if (drag.current === null || drag.current.pointerId !== event.pointerId) return
    setOffset(Math.max(0, event.clientY - drag.current.startY))
  }
  function endDrag(event: PointerEvent<HTMLDivElement>) {
    if (drag.current === null || drag.current.pointerId !== event.pointerId) return
    const far = event.clientY - drag.current.startY > DISMISS_DRAG_PX
    drag.current = null
    setDragging(false)
    setOffset(0)
    // A pointercancel (the browser took the gesture for a scroll) closes nothing.
    if (far && event.type === 'pointerup') onClose()
  }

  return (
    <DialogPrimitive.Root open onOpenChange={(open) => !open && onClose()}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay
          data-slot="bottom-sheet-overlay"
          className="fixed inset-0 z-40 bg-ink/40"
        />
        <DialogPrimitive.Content
          data-slot="bottom-sheet"
          aria-describedby={undefined}
          onCloseAutoFocus={(event) => event.preventDefault()}
          onPointerDown={startDrag}
          onPointerMove={moveDrag}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          style={offset === 0 ? undefined : { transform: `translateY(${offset}px)` }}
          className={cn(
            'fixed inset-x-0 top-3 bottom-0 z-50 flex flex-col overflow-hidden rounded-t-xl border border-b-0 border-border bg-surface-raised text-ink shadow-md outline-none',
            !dragging && 'transition-transform',
            className,
          )}
        >
          <div
            data-slot="bottom-sheet-handle"
            aria-hidden="true"
            className="flex h-6 flex-none cursor-grab touch-none items-center justify-center"
          >
            <span className="h-1 w-10 rounded-full bg-border-strong" />
          </div>
          {/* A header here is a drag target, so a touch on it must not scroll the page. */}
          <div className="min-h-0 flex-1 [&_header]:touch-none">{children}</div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

export { BottomSheet, SheetTitle }
export type { BottomSheetProps }
