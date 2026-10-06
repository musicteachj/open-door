import { useCallback, useLayoutEffect, useState } from 'react'

/**
 * Whether an element's text is cut off by an ellipsis: its content is wider than its box. Attach
 * the returned ref to the element that carries `truncate`. It checks on mount, whenever the
 * element is resized, and whenever `watch` (the text shown) changes. Resizing alone isn't enough,
 * because a new title in a box of the same width doesn't resize anything.
 */
export function useIsTruncated<T extends HTMLElement>(watch?: unknown) {
  const [element, setElement] = useState<T | null>(null)
  const [truncated, setTruncated] = useState(false)
  const ref = useCallback((node: T | null) => setElement(node), [])

  useLayoutEffect(() => {
    if (!element) return undefined
    const check = () => setTruncated(element.scrollWidth > element.clientWidth)
    check()
    const observer = new ResizeObserver(check)
    observer.observe(element)
    // A web font that arrives late changes the text's width but not the box's, so no resize fires.
    // jsdom has no document.fonts.
    let active = true
    void document.fonts?.ready.then(() => {
      if (active) check()
    })
    return () => {
      active = false
      observer.disconnect()
    }
  }, [element, watch])

  // With no element there is nothing cut off, whatever the last check said.
  return [ref, element !== null && truncated] as const
}
