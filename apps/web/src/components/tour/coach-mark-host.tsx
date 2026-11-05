import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { CoachMark, type CoachMarkProps } from './coach-mark'
import { PHONE_MAX_WIDTH, placeCoachMark, type Placement, type Rect } from './place-coach-mark'
import { TourRing } from './tour-ring'

type CoachMarkHostProps = Omit<CoachMarkProps, 'placement' | 'cardRef' | 'inFlow'> & {
  /** The element the step points at, or null when it is missing (a centered card, no ring). */
  target: HTMLElement | null
  /** Elements the card must not cover: the composer, the result the step is about. */
  avoid?: readonly (HTMLElement | null)[]
  /** Elements the card must never cover, whatever else it costs: the composer. */
  blocked?: readonly (HTMLElement | null)[]
  /**
   * A sticky header over the top of the page, if there is one: what the page shows of itself when
   * the window scrolls starts below it. The host knows no page, so the caller finds it.
   */
  header?: HTMLElement | null
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

/**
 * What the page shows of itself when the window scrolls: below a sticky header, when the caller
 * gives one. The composer's own box is a rectangle to keep clear of, not part of this.
 */
function windowArea(header: HTMLElement | null): Rect {
  const top = header ? Math.max(0, header.getBoundingClientRect().bottom) : 0
  return { x: 0, y: top, width: window.innerWidth, height: window.innerHeight - top }
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

type AreaCache = { current: { target: HTMLElement; area: HTMLElement | null } | null }

/** `scroller`, remembered for the target it was found for. */
function cachedScroller(cache: AreaCache, el: HTMLElement): HTMLElement | null {
  if (cache.current?.target !== el || cache.current.area?.isConnected === false) {
    cache.current = { target: el, area: scroller(el) }
  }
  return cache.current.area
}

/**
 * Puts the coach mark where `placeCoachMark` says: measures the target, the elements to avoid, and
 * the card; draws the ring and the card; and measures again on mount, on every render, on resize,
 * and on any scroll (and when the browser reports a size change, where it can). On a phone it
 * scrolls the target above the sheet; on a desktop it scrolls the target's own scroll area when the
 * target is out of view or the card cannot sit clear of the composer. Both are instant and once per
 * step and target, so the visitor's own scrolling is never fought. When the visitor leaves (the X
 * or Escape), focus returns to what had it before the card opened. Any other unmount leaves focus
 * alone.
 */
function CoachMarkHost({
  target,
  avoid = [],
  blocked = [],
  header = null,
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
  // The target's scroll area, found once per target: finding it walks up the page reading styles,
  // and `measure` runs on every scroll, render, and resize.
  const areaFor = useRef<{ target: HTMLElement; area: HTMLElement | null } | null>(null)
  const deskScrolled = useRef<{ target: HTMLElement | null; step: number } | null>(null)
  const avoidList = useRef(avoid)
  const blockedList = useRef(blocked)
  useLayoutEffect(() => {
    avoidList.current = avoid
    blockedList.current = blocked
  })
  const fallbackRef = useRef(fallbackFocus)
  useLayoutEffect(() => {
    fallbackRef.current = fallbackFocus
  })
  // A stable key for the elements to avoid, so the observer picks up one that mounts later.
  const avoidKey = [...avoid, ...blocked].map((el) => (el ? elementId(el) : 'none')).join(',')

  const measure = useCallback(() => {
    if (cardEl.current === null) return
    const viewport = { width: window.innerWidth, height: window.innerHeight }
    const cardRect = toRect(cardEl.current)
    const mayScroll =
      target !== null &&
      viewport.width > PHONE_MAX_WIDTH &&
      (deskScrolled.current?.target !== target || deskScrolled.current.step !== card.step)
    // The scroll area is looked up only when this measure may scroll; only then can it be used.
    const area = mayScroll ? cachedScroller(areaFor, target) : null
    const scrollBox = mayScroll ? (area ? toRect(area) : windowArea(header)) : null
    const next = placeCoachMark({
      target: target && toRect(target),
      card: cardRect,
      viewport,
      avoid: avoidList.current.flatMap((el) => (el ? [toRect(el)] : [])),
      phone: viewport.width <= PHONE_MAX_WIDTH,
      blocked: blockedList.current.flatMap((el) => (el ? [toRect(el)] : [])),
      scrollArea: scrollBox,
    })
    // Handled on the first measure, whether or not it scrolled: a later scroll of the visitor's
    // own (to reread something above) must never be answered with a scroll of ours.
    if (mayScroll && target !== null) deskScrolled.current = { target, step: card.step }
    if (next.mode === 'anchored' && next.scrollBy && target !== null) {
      const by = { top: next.scrollBy, left: 0, behavior: 'instant' } as const
      if (area) area.scrollBy(by)
      else window.scrollBy(by)
    }
    if (
      next.mode === 'sheet' &&
      next.scrollBy !== 0 &&
      target !== null &&
      (scrolledFor.current?.target !== target ||
        scrolledFor.current.step !== card.step ||
        scrolledFor.current.sheetHeight !== cardRect.height)
    ) {
      scrolledFor.current = { target, step: card.step, sheetHeight: cardRect.height }
      const parent = cachedScroller(areaFor, target)
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
  }, [target, header, card.step])

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
      for (const el of [target, cardEl.current, ...avoidList.current, ...blockedList.current])
        if (el) observer.observe(el)
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
      // Only a control the visitor could have been on is worth returning to. The body, or a page
      // region the app focused itself (`tabindex="-1"`), had it when nothing in particular did.
      if (before instanceof HTMLElement && before.tabIndex >= 0 && before.isConnected) {
        before.focus()
      } else fallbackRef.current?.()?.focus()
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
