// Where the guided tour's coach mark goes. Pure: rectangles in, a placement out, so every rule
// can be tested without a browser. All rectangles are in viewport coordinates (the coach mark is
// drawn `position: fixed`).

type Rect = { x: number; y: number; width: number; height: number }
type Size = { width: number; height: number }

/** The coach mark's width (screen 15, "The coach mark"). */
const CARD_WIDTH = 360
/** The ring is 4 px outside the target and the card is 12 px from the ring. */
const GAP_FROM_TARGET = 16
/** The closest the card comes to the edge of the viewport. */
const MARGIN = 16
/** The width at and below which the tour's cards dock to the bottom as sheets (the design's phone breakpoint). */
const PHONE_MAX_WIDTH = 640
/** The pointer stays this far from the card's corners. */
const POINTER_INSET = 24
/**
 * A target is "small", and the card may sit beside it, when it is at most this wide (a source chip
 * or a button, never the composer or a table). The card then also needs room for its width, the
 * gap, and the margin on the right of the target.
 */
const SMALL_TARGET_MAX_WIDTH = 200

type Side = 'bottom' | 'top' | 'right'

type Placement =
  | {
      mode: 'anchored'
      side: Side
      x: number
      y: number
      pointerOffset: number
      /**
       * Scroll the target's own scroll area by this much (instantly) first; the position assumes
       * it.
       */
      scrollBy?: number
    }
  | { mode: 'centered'; x: number; y: number }
  | { mode: 'sheet'; scrollBy: number }

type PlaceInput = {
  /** The element the step points at, or null when it is missing. */
  target: Rect | null
  /** The card's measured size. */
  card: Size
  viewport: Size
  /** Rectangles the card must not cover: the composer, the result the step is about. */
  avoid: readonly Rect[]
  /** The viewport is 640 px wide or less: dock as a bottom sheet. */
  phone: boolean
  /** Rectangles the card must never cover, whatever else it costs: the composer. */
  blocked?: readonly Rect[]
  /**
   * The visible box of the scroll area the target sits in, when the tour may still scroll it. With
   * it, a target out of view, or one the card cannot sit clear of the blocked rectangles beside,
   * is scrolled so the card fits beneath it.
   */
  scrollArea?: Rect | null
}

/** The space kept between a card and a blocked rectangle. */
const BLOCKED_GAP = 8

/** Keeps `value` in [low, high]; if the range is empty (a card bigger than the room), low wins. */
const keep = (value: number, low: number, high: number) => Math.max(low, Math.min(value, high))

const overlapArea = (a: Rect, b: Rect) =>
  Math.max(0, Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x)) *
  Math.max(0, Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y))

const contains = (outer: Rect, inner: Rect) =>
  inner.x >= outer.x - 1 &&
  inner.y >= outer.y - 1 &&
  inner.x + inner.width <= outer.x + outer.width + 1 &&
  inner.y + inner.height <= outer.y + outer.height + 1

/** Covering the result the target belongs to counts this many times worse than covering anything else. */
const RESULT_WEIGHT = 10

type Candidate = { side: Side; x: number; y: number; pointerOffset: number; hasRoom: boolean }

/** `anchor` is the edge the card sits against (the target, or the result it belongs to). */
function candidate(side: Side, target: Rect, anchor: Rect, card: Size, viewport: Size): Candidate {
  const centerX = target.x + target.width / 2
  const centerY = target.y + target.height / 2
  const maxX = viewport.width - MARGIN - card.width
  const maxY = viewport.height - MARGIN - card.height
  if (side === 'right') {
    const x = anchor.x + anchor.width + GAP_FROM_TARGET
    const y = keep(centerY - card.height / 2, MARGIN, maxY)
    return {
      side,
      // Held inside the window, so a side with no room is measured where the card would really be.
      x: keep(x, MARGIN, maxX),
      y,
      pointerOffset: keep(centerY - y, POINTER_INSET, card.height - POINTER_INSET),
      hasRoom: x <= maxX,
    }
  }
  const x = keep(centerX - card.width / 2, MARGIN, maxX)
  const pointerOffset = keep(centerX - x, POINTER_INSET, card.width - POINTER_INSET)
  if (side === 'bottom') {
    const y = anchor.y + anchor.height + GAP_FROM_TARGET
    return { side, x, y: keep(y, MARGIN, maxY), pointerOffset, hasRoom: y <= maxY }
  }
  const y = anchor.y - GAP_FROM_TARGET - card.height
  return { side, x, y: keep(y, MARGIN, maxY), pointerOffset, hasRoom: y >= MARGIN }
}

/**
 * Chooses the side. Order: right of a small target with room beside it, then below, then above.
 * When the target sits inside one of the rectangles to avoid (the result it belongs to), the card
 * goes against that whole rectangle (right of its right edge, below its bottom, above its top),
 * never inside it, and the pointer still aims at the target's center.
 * The first side that has room and covers nothing to avoid wins. If none does, the side with the
 * least covered area wins (the result counts ten times; ties go to the earlier side); a side with no room is clamped into the
 * viewport and may then cover the target, which counts against it like any other rectangle.
 *
 * On a phone the card is a bottom sheet instead, and the answer is how far to scroll the page so
 * the target, its ring, and the gap sit fully above the sheet (negative if it is above the top).
 */
function placeCoachMark(input: PlaceInput): Placement {
  const { target, card, viewport, avoid, phone, blocked = [], scrollArea = null } = input
  if (phone) {
    if (target === null) return { mode: 'sheet', scrollBy: 0 }
    const sheetTop = viewport.height - card.height
    const bottom = target.y + target.height + GAP_FROM_TARGET
    if (target.y < MARGIN) return { mode: 'sheet', scrollBy: target.y - MARGIN }
    // Never scroll the target's top above the margin to make its bottom fit.
    const needed = Math.max(0, bottom - sheetTop)
    return { mode: 'sheet', scrollBy: Math.min(needed, target.y - MARGIN) }
  }

  if (target === null) {
    return {
      mode: 'centered',
      x: keep((viewport.width - card.width) / 2, MARGIN, viewport.width - MARGIN - card.width),
      y: keep((viewport.height - card.height) / 2, MARGIN, viewport.height - MARGIN - card.height),
    }
  }

  const sides: Side[] =
    target.width <= SMALL_TARGET_MAX_WIDTH ? ['right', 'bottom', 'top'] : ['bottom', 'top']
  // The result the target belongs to: an avoid rect that holds the target. The card goes against
  // the whole result, never inside it.
  const result = avoid.find((r) => contains(r, target)) ?? null
  const anchor = result ?? target
  const boxOf = (c: Candidate): Rect => ({ x: c.x, y: c.y, width: card.width, height: card.height })
  const blockedBy = (box: Rect) => blocked.reduce((sum, rect) => sum + overlapArea(box, rect), 0)
  const candidates = sides.flatMap((side) => {
    const c = candidate(side, target, anchor, card, viewport)
    if (blockedBy(boxOf(c)) === 0) return [c]
    // Last resort: lift the card clear of what it must not cover, even if it then overlaps other
    // content (the target and the result count against it below).
    const lifted = blocked.reduce(
      (y, rect) =>
        overlapArea({ ...boxOf(c), y }, rect) > 0 ? rect.y - BLOCKED_GAP - card.height : y,
      c.y,
    )
    // No room by definition: it is never preferred over a side that has room.
    return [c, { ...c, y: Math.max(MARGIN, lifted), hasRoom: false }]
  })
  const covered = (c: Candidate) =>
    [...avoid, target].reduce(
      (sum, rect) => sum + overlapArea(boxOf(c), rect) * (rect === result ? RESULT_WEIGHT : 1),
      0,
    )
  const clear = candidates.find((c) => c.hasRoom && covered(c) === 0 && blockedBy(boxOf(c)) === 0)

  // Scrolling the target's own area, when it is out of view or nothing is clear: the card then
  // goes beneath the target (or the result it belongs to), with its bottom above the blocked
  // rectangles and the viewport's edge.
  // A target that is, or sits inside, a blocked rectangle (the sticky composer) never moves with
  // the scroll and is always in view: it is never scrolled, and never shifted.
  const stuck = blocked.some((r) => contains(r, target))
  if (scrollArea !== null && !stuck) {
    const limit = Math.min(viewport.height - MARGIN, ...blocked.map((r) => r.y - BLOCKED_GAP))
    const visibleBottom = Math.min(scrollArea.y + scrollArea.height, ...blocked.map((r) => r.y))
    const inView = target.y >= scrollArea.y - 1 && target.y + target.height <= visibleBottom + 1
    if (!inView || clear === undefined) {
      const needed = anchor.y + anchor.height + GAP_FROM_TARGET + card.height - limit
      // Never scroll the target's own top out of the area to make the card fit.
      const keepVisible = target.y - scrollArea.y - MARGIN
      // A target above the area scrolls back just far enough to show it (its top a margin inside);
      // scrolling further up would only push it down for no gain, since the card goes beneath it.
      const aboveArea = target.y < scrollArea.y
      const scrollBy = Math.round(aboveArea ? keepVisible : Math.min(needed, keepVisible))
      // A target in view only scrolls down to make room beneath it: never up for no gain.
      if (scrollBy !== 0 && (!inView || scrollBy > 0)) {
        // Only the target and the result move with the scroll. The blocked rectangles are taken
        // to be fixed or sticky (the composer is), so they stay where they are. The host measures
        // again on the scroll event it causes, so a blocked rectangle that did move is corrected
        // on the next read.
        const moved = (r: Rect): Rect => ({ ...r, y: r.y - scrollBy })
        const after = placeCoachMark({
          ...input,
          target: moved(target),
          avoid: avoid.map(moved),
          scrollArea: null,
        })
        if (after.mode === 'anchored') return { ...after, scrollBy }
      }
    }
  }

  const rank = (c: Candidate) => [blockedBy(boxOf(c)), covered(c)] as const
  const better = (a: Candidate, b: Candidate) => {
    const [ah, as] = rank(a)
    const [bh, bs] = rank(b)
    return ah !== bh ? ah < bh : as < bs
  }
  const chosen =
    clear ?? candidates.reduce((best, c) => (better(c, best) ? c : best), candidates[0]!)
  return {
    mode: 'anchored',
    side: chosen.side,
    x: chosen.x,
    y: chosen.y,
    pointerOffset: chosen.pointerOffset,
  }
}

export {
  CARD_WIDTH,
  GAP_FROM_TARGET,
  MARGIN,
  PHONE_MAX_WIDTH,
  POINTER_INSET,
  SMALL_TARGET_MAX_WIDTH,
  placeCoachMark,
}
export type { PlaceInput, Placement, Rect, Side, Size }
