import { useCallback, useLayoutEffect, useRef, useState } from 'react'

/**
 * Opens and closes the case form in place of "Open a confidential case", and returns focus to the
 * button when the person presses "Not now". The button unmounts while the form is open, so its
 * ref points at the new button once the form has gone, and focus moves there in the same commit.
 *
 * `open` and `close` are for the button and the form's own "Not now". A form that closes because
 * a case was sent does not return focus: the sent line takes it.
 */
function useCaseDisclosure() {
  const [isOpen, setIsOpen] = useState(false)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const returnFocus = useRef(false)

  useLayoutEffect(() => {
    if (!isOpen && returnFocus.current) {
      returnFocus.current = false
      buttonRef.current?.focus()
    }
  }, [isOpen])

  const open = useCallback(() => setIsOpen(true), [])
  /** "Not now": closes the form and returns focus to the button that opened it. */
  const close = useCallback(() => {
    returnFocus.current = true
    setIsOpen(false)
  }, [])
  /** Closes the form without moving focus. */
  const dismiss = useCallback(() => setIsOpen(false), [])
  return { isOpen, open, close, dismiss, buttonRef }
}

export { useCaseDisclosure }
