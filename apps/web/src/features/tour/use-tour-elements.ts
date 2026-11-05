import { useEffect, useState } from 'react'
import { TOUR_TARGETS } from '@/lib/tour-targets'
import { turnKey } from '@/lib/turn-key'
import type { TourStep } from './script'

type TourElements = {
  /** What the coach mark points at: the last of the step's targets that is on the page. */
  target: HTMLElement | null
  /** The page's sticky header, which hides what scrolls under it: the conversation's, if any. */
  header: HTMLElement | null
  /** The composer, which the card must never cover. */
  composer: HTMLElement | null
  /**
   * What the card must not cover: the step's expected result (the confirm card or the HR panel),
   * or else the latest answer, when it is on the page.
   */
  result: HTMLElement | null
  /**
   * The step's expected card or panel that belongs to the given turn, which is the step's result
   * proper. Null without a turn, or while the turn has none on the page.
   */
  own: HTMLElement | null
}

const RESULT_SLOT = { card: 'confirm-card', panel: 'escalation-panel' } as const
/** The element that carries a turn's ID and holds its card (the cards' row) or is its panel. */
const OWNER_SLOT = { card: 'proposal-cards', panel: 'escalation-panel' } as const

/** Targets where any row will do: the first on the page is taken, for a stable choice. */
const FIRST_IN_ORDER: ReadonlySet<string> = new Set([TOUR_TARGETS.flaggedRow])

/** The tour's own parts, which may sit inside the watched area. */
const OWN_SLOTS = '[data-slot="coach-mark"], [data-slot="tour-ring"]'

const all = (selector: string) => [...document.querySelectorAll<HTMLElement>(selector)]
const latest = (selector: string) => all(selector).at(-1) ?? null

/**
 * The latest element carrying a `data-tour` name (the first, for a target where any row will do).
 * For the source chip it is the first chip under the latest answer that has any, which is the one
 * the step is about (the section the question hits first), not a chip of an older answer.
 */
function findTarget(name: string): HTMLElement | null {
  // Any flagged, non-abandoned row is the sensitive message the step describes. The server orders
  // a day's flagged rows by ID on purpose (a flagged row hides its time), so "first" is not
  // "newest": it is only a stable choice.
  if (FIRST_IN_ORDER.has(name)) return document.querySelector<HTMLElement>(`[data-tour="${name}"]`)
  const last = latest(`[data-tour="${name}"]`)
  if (last === null || name !== TOUR_TARGETS.sourceChip) return last
  const row = last.closest('[data-slot="source-chips"]')
  return row?.querySelector<HTMLElement>(`[data-tour="${name}"]`) ?? last
}

/**
 * The step's expected card or panel in the given turn, or in a later turn of the conversation (a
 * question asked again, or typed, after the chip's): one that follows the chip's question in the
 * page. A card or panel of an earlier turn, however many are on the page, is never it.
 */
function findOwn(step: TourStep, turnId: string | null): HTMLElement | null {
  if (step.expect === undefined || turnId === null) return null
  const key = turnKey(turnId)
  const start = all('[data-slot="user-message"]').find((el) => el.dataset.turnKey === key)
  const owners = all(`[data-slot="${OWNER_SLOT[step.expect]}"]`).filter(
    (el) =>
      el.dataset.turnKey === key ||
      (start !== undefined &&
        el.dataset.turnKey !== undefined &&
        (start.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0),
  )
  for (const owner of owners.reverse()) {
    const found =
      owner.dataset.slot === RESULT_SLOT[step.expect]
        ? owner
        : owner.querySelector<HTMLElement>(`[data-slot="${RESULT_SLOT[step.expect]}"]`)
    if (found !== null) return found
  }
  return null
}

/** Reads the page for the step's elements; `turnId` is the step's last chip's turn, if known. */
export function findTourElements(step: TourStep, turnId: string | null = null): TourElements {
  let target: HTMLElement | null = null
  for (const name of [...step.targets].reverse()) {
    target = findTarget(name)
    if (target !== null) break
  }
  const own = findOwn(step, turnId)
  const resultSelector = `[data-slot="${step.expect === undefined ? 'assistant-message' : RESULT_SLOT[step.expect]}"]`
  return {
    target,
    header: document.querySelector('[data-slot="conversation-header"]')?.parentElement ?? null,
    composer: findTarget(TOUR_TARGETS.composer),
    result: own ?? latest(resultSelector),
    own,
  }
}

const NONE: TourElements = {
  target: null,
  header: null,
  composer: null,
  result: null,
  own: null,
}

const same = (a: TourElements, b: TourElements) =>
  a.target === b.target &&
  a.header === b.header &&
  a.composer === b.composer &&
  a.result === b.result &&
  a.own === b.own

/**
 * The step's elements, read again whenever the page changes (an answer streams in, a card
 * appears, a route renders). The reads are batched to one per animation frame, and the state
 * changes only when an element does.
 */
export function useTourElements(
  step: TourStep,
  turnId: string | null,
  enabled: boolean,
): TourElements {
  const [read, setRead] = useState<{ step: string; elements: TourElements } | null>(null)
  useEffect(() => {
    if (!enabled) return
    let frame = 0
    const readNow = () => {
      frame = 0
      const next = findTourElements(step, turnId)
      setRead((current) =>
        current?.step === step.id && same(current.elements, next)
          ? current
          : { step: step.id, elements: next },
      )
    }
    readNow()
    const observer = new MutationObserver((records) => {
      // The coach mark and its ring redraw on every measure: they are never what is read.
      if (records.every((r) => r.target instanceof Element && r.target.closest(OWN_SLOTS))) return
      if (frame === 0) frame = requestAnimationFrame(readNow)
    })
    // The page's main area holds every target, the composer, and the result. The rest of the
    // document (the sidebar, the rail, the coach mark itself) never changes what is read, so its
    // churn does not cost a full scan. Without a main area (a page of its own), the whole body.
    observer.observe(document.querySelector('main') ?? document.body, {
      childList: true,
      subtree: true,
      // A target can also appear by an existing element taking the attribute.
      attributes: true,
      attributeFilter: ['data-tour'],
    })
    return () => {
      observer.disconnect()
      if (frame !== 0) cancelAnimationFrame(frame)
    }
  }, [step, turnId, enabled])
  // What was read for the step before is not this step's, for the render before it is read again.
  return read?.step === step.id ? read.elements : NONE
}
