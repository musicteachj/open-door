import { describe, expect, it } from 'vitest'
import { CARD_WIDTH, GAP_FROM_TARGET, MARGIN, placeCoachMark, type Rect } from './place-coach-mark'

const VIEWPORT = { width: 1440, height: 900 }
const CARD = { width: CARD_WIDTH, height: 240 }
const rect = (x: number, y: number, width: number, height: number): Rect => ({
  x,
  y,
  width,
  height,
})

const overlaps = (a: Rect, b: Rect) =>
  a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height

function anchored(placement: ReturnType<typeof placeCoachMark>) {
  if (placement.mode !== 'anchored') throw new Error(`expected anchored, got ${placement.mode}`)
  return placement
}
const place = (
  target: Rect | null,
  over: { avoid?: Rect[]; viewport?: typeof VIEWPORT; card?: typeof CARD } = {},
) =>
  placeCoachMark({
    target,
    card: over.card ?? CARD,
    viewport: over.viewport ?? VIEWPORT,
    avoid: over.avoid ?? [],
    phone: false,
  })

describe('placeCoachMark', () => {
  it('sits below a wide target by default, 16 px from it (4 for the ring, 12 gap)', () => {
    const target = rect(300, 200, 700, 56)
    const p = anchored(place(target))
    expect(p.side).toBe('bottom')
    expect(p.y).toBe(target.y + target.height + GAP_FROM_TARGET)
    expect(GAP_FROM_TARGET).toBe(16)
  })

  it('is centered on the target across the edge it sits on', () => {
    const target = rect(300, 200, 700, 56)
    const p = anchored(place(target))
    expect(p.x).toBe(650 - CARD_WIDTH / 2)
    expect(p.pointerOffset).toBe(CARD_WIDTH / 2)
  })

  it('points at the target center, wherever the card had to shift', () => {
    const target = rect(20, 200, 300, 40)
    const p = anchored(place(target))
    expect(p.x).toBe(MARGIN)
    // The center is at 170, so 154 px along a card that starts at 16.
    expect(p.pointerOffset).toBe(154)
  })

  it('keeps the pointer away from the corners', () => {
    // Something to the right of the target rules out that side, so the card goes below.
    const left = anchored(place(rect(16, 200, 24, 24), { avoid: [rect(60, 100, 400, 100)] }))
    expect(left.side).toBe('bottom')
    expect(left.pointerOffset).toBe(24)
    const right = anchored(place(rect(1400, 200, 24, 24)))
    expect(right.x).toBe(VIEWPORT.width - CARD_WIDTH - MARGIN)
    expect(right.pointerOffset).toBe(CARD_WIDTH - 24)
  })

  it('goes above when there is no room below', () => {
    const target = rect(300, 780, 700, 56)
    const p = anchored(place(target))
    expect(p.side).toBe('top')
    expect(p.y).toBe(target.y - GAP_FROM_TARGET - CARD.height)
  })

  it('goes to the right of a small target when there is room beside it', () => {
    const target = rect(400, 300, 120, 32)
    const p = anchored(place(target))
    expect(p.side).toBe('right')
    expect(p.x).toBe(target.x + target.width + GAP_FROM_TARGET)
    expect(p.y).toBe(316 - CARD.height / 2)
    expect(p.pointerOffset).toBe(CARD.height / 2)
  })

  it('treats a target 200 px wide as small and 201 px as not', () => {
    expect(anchored(place(rect(400, 300, 200, 32))).side).toBe('right')
    expect(anchored(place(rect(400, 300, 201, 32))).side).toBe('bottom')
  })

  it('does not go right of a small target without room for the card and its margin', () => {
    const target = rect(1440 - 120 - 100, 300, 120, 32)
    const roomNeeded = target.x + target.width + GAP_FROM_TARGET + CARD_WIDTH + MARGIN
    expect(roomNeeded).toBeGreaterThan(VIEWPORT.width)
    expect(anchored(place(target)).side).toBe('bottom')
    const exact = rect(VIEWPORT.width - MARGIN - CARD_WIDTH - GAP_FROM_TARGET - 120, 300, 120, 32)
    expect(anchored(place(exact)).side).toBe('right')
  })

  it('keeps a right-side card inside the viewport vertically', () => {
    const p = anchored(place(rect(400, 10, 120, 32)))
    expect(p.side).toBe('right')
    expect(p.y).toBe(MARGIN)
    // The center is 10 px below the card's top, closer than the corner allowance.
    expect(p.pointerOffset).toBe(24)
  })

  it('tries below before above when both are clear', () => {
    const target = rect(300, 400, 700, 56)
    expect(anchored(place(target, { avoid: [rect(0, 0, 100, 100)] })).side).toBe('bottom')
  })

  it('skips below when something to avoid is there, and takes above', () => {
    const target = rect(300, 400, 700, 56)
    const below = rect(300, 472, 700, 100)
    const p = anchored(place(target, { avoid: [below] }))
    expect(p.side).toBe('top')
    expect(p.y).toBe(target.y - GAP_FROM_TARGET - CARD.height)
  })

  it('skips the right of a small target when it would cover something to avoid', () => {
    const target = rect(400, 300, 120, 32)
    const beside = rect(540, 260, 500, 60)
    const p = anchored(place(target, { avoid: [beside] }))
    expect(p.side).not.toBe('right')
    expect(overlaps(rect(p.x, p.y, CARD.width, CARD.height), beside)).toBe(false)
  })

  describe('a target inside the result it belongs to', () => {
    // The gallery at 1440 x 900: a full-width sample card with its Confirm button, the composer below.
    const result = rect(232, 420, 976, 150)
    const confirm = rect(248, 520, 84, 40)
    const composer = rect(232, 586, 976, 64)

    it('goes above the result, never inside it, and clear of the composer', () => {
      const p = anchored(place(confirm, { avoid: [composer, result] }))
      const box = rect(p.x, p.y, CARD.width, CARD.height)
      expect(p.side).toBe('top')
      expect(p.y).toBe(result.y - GAP_FROM_TARGET - CARD.height)
      expect(overlaps(box, result)).toBe(false)
      expect(overlaps(box, composer)).toBe(false)
    })

    it('still points at the target, not at the result', () => {
      const p = anchored(place(confirm, { avoid: [composer, result] }))
      // Confirm's center is at 290: the card is centered on it, and the pointer is at its middle.
      expect(p.x).toBe(290 - CARD_WIDTH / 2)
      expect(p.pointerOffset).toBe(CARD_WIDTH / 2)
    })

    it('goes below the result when the composer is not there and the top has no room', () => {
      const high = rect(232, 40, 976, 150)
      const p = anchored(place(rect(248, 140, 84, 40), { avoid: [high] }))
      expect(p.side).toBe('bottom')
      expect(p.y).toBe(high.y + high.height + GAP_FROM_TARGET)
    })

    it('goes to the right of a narrow result, level with the target', () => {
      const narrow = rect(100, 300, 400, 150)
      const small = rect(120, 400, 84, 32)
      const p = anchored(place(small, { avoid: [narrow] }))
      expect(p.side).toBe('right')
      expect(p.x).toBe(narrow.x + narrow.width + GAP_FROM_TARGET)
    })

    it('counts covering the result as worse than covering other page content', () => {
      // No side is clear. Above is clamped to the top of the screen and bites 156 rows into the
      // result (56,160 px squared); below only bites a large unrelated block (84,960). Unweighted,
      // above would win; the result must count for more.
      const res = rect(0, 100, 1440, 300)
      const target = rect(100, 300, 84, 40)
      const unrelated = rect(0, 420, 1440, 400)
      const p = anchored(place(target, { avoid: [res, unrelated] }))
      expect(p.side).toBe('bottom')
      expect(overlaps(rect(p.x, p.y, CARD.width, CARD.height), res)).toBe(false)
    })
  })

  it('picks the side with the least overlap when all of them overlap', () => {
    const target = rect(300, 400, 700, 56)
    // A small bite out of the space above, a large one below, a huge one to the right is not tried.
    const above = rect(300, 100, 700, 280)
    const belowLarge = rect(300, 472, 700, 400)
    const p = anchored(place(target, { avoid: [above, belowLarge] }))
    const cardRect = rect(p.x, p.y, CARD.width, CARD.height)
    const area = (r: Rect) =>
      Math.max(
        0,
        Math.min(cardRect.x + cardRect.width, r.x + r.width) - Math.max(cardRect.x, r.x),
      ) *
      Math.max(
        0,
        Math.min(cardRect.y + cardRect.height, r.y + r.height) - Math.max(cardRect.y, r.y),
      )
    const chosen = area(above) + area(belowLarge)
    expect(chosen).toBeGreaterThan(0)
    // Below would have overlapped more than above.
    expect(p.side).toBe('top')
  })

  it('breaks a tie in overlap by the order below, above', () => {
    const target = rect(300, 400, 700, 56)
    const p = anchored(
      place(target, {
        avoid: [rect(0, 0, 1440, 900)],
      }),
    )
    // Everything overlaps the same way; the default side wins.
    expect(p.side).toBe('bottom')
  })

  it('still places the card when no side has room, clamped inside the viewport', () => {
    const tall = { width: 360, height: 700 }
    const p = anchored(place(rect(300, 400, 700, 56), { card: tall }))
    expect(p.y).toBeGreaterThanOrEqual(MARGIN)
    expect(p.y + tall.height).toBeLessThanOrEqual(VIEWPORT.height - MARGIN)
  })

  it('clamps horizontally inside the viewport with a 16 px margin', () => {
    const p = anchored(place(rect(1300, 200, 400, 40)))
    expect(p.x + CARD_WIDTH).toBeLessThanOrEqual(VIEWPORT.width - MARGIN)
    const q = anchored(place(rect(-100, 200, 100, 40)))
    expect(q.x).toBe(MARGIN)
  })

  it('centers the card in the viewport when there is no target', () => {
    const p = place(null)
    expect(p).toEqual({
      mode: 'centered',
      x: (VIEWPORT.width - CARD_WIDTH) / 2,
      y: (VIEWPORT.height - CARD.height) / 2,
    })
  })

  it('keeps a centered card inside a viewport smaller than the card', () => {
    const p = placeCoachMark({
      target: null,
      card: { width: 360, height: 500 },
      viewport: { width: 700, height: 400 },
      avoid: [],
      phone: false,
    })
    expect(p).toEqual({ mode: 'centered', x: 170, y: MARGIN })
  })
})

describe('placeCoachMark on a phone', () => {
  const phone = { width: 390, height: 844 }
  const sheet = { width: 390, height: 260 }
  const run = (target: Rect | null) =>
    placeCoachMark({ target, card: sheet, viewport: phone, avoid: [], phone: true })

  it('docks as a sheet and leaves the page alone when the target is already above it', () => {
    expect(run(rect(16, 300, 358, 56))).toEqual({ mode: 'sheet', scrollBy: 0 })
  })

  it('scrolls the page so the target (and its ring and gap) sits above the sheet', () => {
    // The sheet starts at 844 - 260 = 584. The target ends at 700; with 16 px it needs 716 - 584.
    expect(run(rect(16, 644, 358, 56))).toEqual({ mode: 'sheet', scrollBy: 132 })
  })

  it('needs no scroll when the target ends exactly 16 px above the sheet', () => {
    expect(run(rect(16, 512, 358, 56))).toEqual({ mode: 'sheet', scrollBy: 0 })
  })

  it('does not scroll the target off the top of the screen', () => {
    // A target taller than the room: show its top, 16 px from the edge.
    expect(run(rect(16, 100, 358, 700))).toEqual({ mode: 'sheet', scrollBy: 84 })
  })

  it('scrolls back when the target is above the top of the screen', () => {
    expect(run(rect(16, -200, 358, 56))).toEqual({ mode: 'sheet', scrollBy: -216 })
  })

  it('has nothing to scroll with no target', () => {
    expect(run(null)).toEqual({ mode: 'sheet', scrollBy: 0 })
  })

  it('docks at 640 px and below and not above, by the caller passing phone', () => {
    expect(
      placeCoachMark({
        target: rect(100, 100, 100, 40),
        card: CARD,
        viewport: { width: 641, height: 800 },
        avoid: [],
        phone: false,
      }).mode,
    ).toBe('anchored')
  })
})
