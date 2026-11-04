import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { CoachMark, type CoachMarkProps } from './coach-mark'
import { PHONE_MAX_WIDTH, placeCoachMark, type Placement, type Rect } from './place-coach-mark'
import { TourRing } from './tour-ring'

type CoachMarkHostProps = Omit<CoachMarkProps, 'placement' | 'cardRef' | 'inFlow'> & {
  /** The element the step points at, or null when it is missing (a centered card, no ring). */
  target: HTMLElement | null
  /** Elements the card must not cover: the composer, the result the step is about. */
  avoid?: readonly (HTMLElement | null)[]
  /** Where focus goes on leaving when the element that had it before the tour is gone. */
  fallbackFocus?: () => HTMLElement | null
}

const ids = new WeakMap<Element, number>()
let nextId = 1
/** A number that stays the same for an element, so a list of them can be compared as a string. */
function elementId(el: Element) {
  if (!ids.has(el)) ids.set(el, nextId++)
  return ids.get(el)
}

const toRect = (el: Element): Rect => {
  const { x, y, width, height } = el.getBoundingClientRect()
  return { x, y, width, height }
}

/** The nearest ancestor that scrolls vertically, or null for the window. */
function scroller(el: HTMLElement): HTMLElement | null {
  for (let node = el.parentElement; node; node = node.parentElement) {
    const { overflowY } = getComputedStyle(node)
    if ((overflowY === 'auto' || overflowY === 'scroll') && node.scrollHeight > node.clientHeight) {
      return node
    }
  }
  return null
}

/**
 * Puts the coach mark where `placeCoachMark` says: measures the target, the elements to avoid, and
 * the card; draws the ring and the card; and measures again on mount, on every render, on resize,
 * and on any scroll (and when the browser reports a size change, where it can). On a phone it
 * scrolls the target above the sheet, instantly and once per step and target, so the visitor's own
 * scrolling is never fought. When the visitor leaves (the X or Escape), focus returns to what had
 * it before the card opened. Any other unmount leaves focus alone.
 */
function CoachMarkHost({
  target,
  avoid = [],
  fallbackFocus,
  onLeave,
  ...card
}: CoachMarkHostProps) {
  const cardEl = useRef<HTMLDivElement>(null)
  const [placement, setPlacement] = useState<Placement>({ mode: 'centered', x: 0, y: 0 })
  const [ringRect, setRingRect] = useState<Rect | null>(null)
  const [ringRadius, setRingRadius] = useState(8)
  // Read while rendering, before the card's own effect moves focus to its title.
  const [before] = useState(() => document.activeElement)
  const leaving = useRef(false)
  const scrolledFor = useRef<{
    target: HTMLElement | null
    step: number
    sheetHeight: number
  } | null>(null)
  const avoidList = useRef(avoid)
  useLayoutEffect(() => {
    avoidList.current = avoid
  })
  const fallbackRef = useRef(fallbackFocus)
  useLayoutEffect(() => {
    fallbackRef.current = fallbackFocus
  })
  // A stable key for the elements to avoid, so the observer picks up one that mounts later.
  const avoidKey = avoid.map((el) => (el ? elementId(el) : 'none')).join(',')

  const measure = useCallback(() => {
    if (cardEl.current === null) return
    const viewport = { width: window.innerWidth, height: window.innerHeight }
    const cardRect = toRect(cardEl.current)
    const next = placeCoachMark({
      target: target && toRect(target),
      card: cardRect,
      viewport,
      avoid: avoidList.current.flatMap((el) => (el ? [toRect(el)] : [])),
      phone: viewport.width <= PHONE_MAX_WIDTH,
    })
    if (
      next.mode === 'sheet' &&
      next.scrollBy !== 0 &&
      target !== null &&
      (scrolledFor.current?.target !== target ||
        scrolledFor.current.step !== card.step ||
        scrolledFor.current.sheetHeight !== cardRect.height)
    ) {
      scrolledFor.current = { target, step: card.step, sheetHeight: cardRect.height }
      const parent = scroller(target)
      if (parent) parent.scrollBy({ top: next.scrollBy, left: 0, behavior: 'instant' })
      else window.scrollBy({ top: next.scrollBy, left: 0, behavior: 'instant' })
    }
    const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)
    setPlacement((current) => (same(current, next) ? current : next))
    const rect = target && toRect(target)
    setRingRect((current) => (same(current, rect) ? current : rect))
    if (target) {
      const radius = parseFloat(getComputedStyle(target).borderTopLeftRadius)
      setRingRadius(Number.isNaN(radius) ? 8 : radius)
    }
  }, [target, card.step])

  // After every render, so a new step's size (or a changed target) is measured at once. It sets
  // state only when the answer changed, so it settles.
  useLayoutEffect(() => {
    measure()
  })

  useEffect(() => {
    const options = { capture: true, passive: true } as const
    window.addEventListener('resize', measure)
    document.addEventListener('scroll', measure, options)
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure)
    if (observer) {
      for (const el of [target, cardEl.current, ...avoidList.current]) if (el) observer.observe(el)
    }
    return () => {
      window.removeEventListener('resize', measure)
      document.removeEventListener('scroll', measure, options)
      observer?.disconnect()
    }
  }, [measure, target, avoidKey])

  useEffect(
    () => () => {
      if (!leaving.current) return
      if (before instanceof HTMLElement && before.isConnected) before.focus()
      else fallbackRef.current?.()?.focus()
    },
    [before],
  )

  return (
    <>
      <TourRing rect={ringRect} radius={ringRadius} />
      <CoachMark
        {...card}
        placement={placement}
        cardRef={cardEl}
        onLeave={() => {
          leaving.current = true
          onLeave()
        }}
      />
    </>
  )
}

export { CoachMarkHost }
export type { CoachMarkHostProps }
