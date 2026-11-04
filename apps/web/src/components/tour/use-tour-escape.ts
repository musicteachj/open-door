import { useEffect, useRef } from 'react'

/**
 * Elements that take Escape for themselves first: an open menu, a list, an alert dialog, a modal,
 * and any open Radix dialog (a bottom sheet, the passage sheet), which sets `role="dialog"` and
 * `data-state="open"` but not `aria-modal`. The tour's own cards are `role="dialog"` too, marked
 * `data-tour-own`, so they never count.
 */
const OWN_ESCAPE =
  '[role="menu"], [role="alertdialog"], [role="listbox"], [aria-modal="true"], [role="dialog"][data-state="open"]:not([data-tour-own])'

/**
 * Calls `onEscape` for Escape from anywhere on the page, unless something else is open that
 * closes with it (Radix closes that first), an IME composition is ending, or `enabled` is false.
 */
function useTourEscape(onEscape: () => void, enabled = true) {
  const ref = useRef(onEscape)
  useEffect(() => {
    ref.current = onEscape
  })
  useEffect(() => {
    if (!enabled) return
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== 'Escape' || event.isComposing) return
      if (document.querySelector(OWN_ESCAPE) !== null) return
      event.preventDefault()
      ref.current()
    }
    // Capture, so it runs before a Radix menu or dialog opened later closes itself (which can
    // remove it from the page before a bubbling listener looks).
    document.addEventListener('keydown', onKeyDown, true)
    return () => document.removeEventListener('keydown', onKeyDown, true)
  }, [enabled])
}

export { useTourEscape }
