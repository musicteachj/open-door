// Where focus goes when the source panel closes: the marker or chip that opened it, the newest one
// if the panel was reused for another passage. The panel lives in the shell and the markers in the
// page, so this is the one thing they share. It holds the element for as long as the panel is
// open and no longer: it is forgotten when the conversation page goes away, and when who is
// signed in changes. If the page was redrawn and the element is gone, the same passage's marker
// (or chip) is found by `data-passage-id`.

import { registerReset } from '@/lib/identity'

let opener: { element: Element | null; key: string } | null = null

/** The marker or chip that was just pressed to open `key`. */
export function rememberOpener(element: Element | null, key: string): void {
  opener = { element, key }
}

/** Puts focus back on the opener, and forgets it. Does nothing if there is none to find. */
export function returnFocusToOpener(): void {
  const remembered = opener
  opener = null
  if (remembered === null) return
  const target =
    remembered.element?.isConnected === true
      ? remembered.element
      : [
          ...document.querySelectorAll<HTMLElement>(
            '[data-slot="citation-marker"][data-passage-id], [data-slot="source-chip"][data-passage-id]',
          ),
        ].find((candidate) => candidate.dataset.passageId === remembered.key)
  if (target instanceof HTMLElement) target.focus()
}

/** Drops the opener without moving focus (the page went away, or the identity changed). */
export function forgetOpener(): void {
  opener = null
}

// A switch or sign-out unmounts the page, but an element held here must not outlive the person.
registerReset(forgetOpener)
