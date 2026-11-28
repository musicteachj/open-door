import { useEffect, useRef, useState } from 'react'
import { useMediaQuery } from '@/hooks/use-media-query'

/** Pacing is on only where the person has not asked for less motion (and so never in jsdom). */
export const MOTION_ALLOWED_QUERY = '(prefers-reduced-motion: no-preference)'

/** The slowest the text is revealed, in characters a millisecond: about as fast as a model writes. */
const MIN_CHARACTERS_PER_MS = 0.2
/** However much text is waiting, it is all shown within this long. */
const CATCH_UP_MS = 500
/**
 * A piece of text this short or shorter shows at once, as the model's own streaming arrives: only a
 * real burst is paced, so ordinary streaming doesn't re-render the answer on every frame.
 */
const INSTANT_CHARACTERS = 48

/** One frame at 60 frames a second, for the first frame of a reveal, which has none before it. */
const FRAME_MS = 16

/** A reveal that would stop this close before a space goes on to it, so words appear whole. */
const WORD_SNAP_CHARACTERS = 12

/** Where to stop at or after `count`: the end of a word nearby, and never inside a surrogate pair. */
function stopAt(text: string, count: number): number {
  if (count >= text.length) return text.length
  let end = count
  const limit = Math.min(text.length, count + WORD_SNAP_CHARACTERS)
  while (end < limit && !/\s/.test(text[end] ?? '')) end++
  if (end === limit && end < text.length && !/\s/.test(text[end] ?? '')) end = count
  const code = text.charCodeAt(end - 1)
  if (code >= 0xd800 && code <= 0xdbff) end++
  return Math.min(end, text.length)
}

/**
 * How much of each turn's text is shown, while its reveal is still going. A turn is drawn by a new
 * component as it moves from live to settling to saved, and each takes over from here, so the
 * reveal carries on instead of starting again or jumping to the end.
 */
const progress = new Map<string, number>()

type RevealedText = {
  /** The part of the text to show now. */
  text: string
  /** True while some of the text that has arrived is not shown yet. */
  revealing: boolean
}

/**
 * The answer's text, played out at a steady pace while it streams (ADR 0025). The model's own
 * streaming looks the same, but a large piece that arrives at once (the server sends a restored
 * answer in one event) is revealed over at most half a second instead of landing all at once.
 *
 * Only text that arrives while the message is mounted and streaming is paced: a finished answer
 * from the history, or text already shown before a remount, shows whole. A text that does not continue what was shown (a `text.retracted` event and what follows)
 * starts again from nothing. Under reduced motion, with no `matchMedia`, or once the answer is
 * stopped or failed (`settled`), the text shows whole.
 */
export function useRevealedText(
  text: string,
  streaming: boolean,
  /** Show the whole text now and pace nothing more: the answer was stopped or failed. */
  settled = false,
  /** The turn the text belongs to, so a reveal carries on when another component takes the turn over. */
  key?: string | null,
): RevealedText {
  const motionAllowed = useMediaQuery(MOTION_ALLOWED_QUERY)
  // Whether this message ever streamed while mounted: only then is its text paced.
  // A reveal another component started for this turn carries on from where it was.
  const [carried] = useState(() => (key ? progress.get(key) : undefined))
  const [paced, setPaced] = useState(streaming || carried !== undefined)
  if (streaming && !paced) setPaced(true)
  // Text already there when the message mounts shows at once (a remount mid-stream never replays
  // it); only what arrives after is paced. A question just sent starts empty, so all of it is.
  const [count, setCount] = useState(carried ?? text.length)
  // The text the count belongs to, so a retraction (text that does not continue it) starts over.
  const [countedText, setCountedText] = useState(text)
  // The count this render works from: every rule below reads the one before it, not the stale state.
  let next = count
  if (countedText !== text) {
    const shownBefore = countedText.slice(0, Math.min(count, countedText.length))
    setCountedText(text)
    if (!text.startsWith(shownBefore)) next = 0
  }

  const active = paced && motionAllowed && !settled
  // While nothing is paced, the count follows the text, so allowing motion again later never hides
  // text that was already showing.
  if (!active) next = text.length
  // A short piece waiting shows at once (a burst's last few words too).
  else if (next < text.length && text.length - next <= INSTANT_CHARACTERS) next = text.length
  if (next !== count) setCount(next)
  const target = text.length
  const shown = active ? Math.min(next, target) : target

  // Characters a millisecond. It rises when more text waits than the catch-up allows, and falls
  // back to the minimum once everything is shown.
  const speed = useRef(MIN_CHARACTERS_PER_MS)
  // The time of the frame that last revealed text, kept across renders so each step measures the
  // time since the one before. Null while nothing is waiting.
  const lastFrame = useRef<number | null>(null)
  // Unmounting forgets the turn's place. A component that takes the turn over has already read it
  // while rendering, so it carries on, and a turn drawn again later never replays its reveal.
  useEffect(
    () => () => {
      if (key) progress.delete(key)
    },
    [key],
  )
  // Record how far this turn's reveal has got, for whichever component draws the turn next.
  useEffect(() => {
    if (!key) return
    if (active && shown < target) progress.set(key, shown)
    else progress.delete(key)
  }, [key, active, shown, target])
  useEffect(() => {
    if (!active || shown >= target) {
      speed.current = MIN_CHARACTERS_PER_MS
      lastFrame.current = null
      return
    }
    speed.current = Math.max(speed.current, (target - shown) / CATCH_UP_MS)
    const frame = requestAnimationFrame((now) => {
      // The first frame of a reveal counts as one frame's worth of time.
      const elapsed = now - (lastFrame.current ?? now - FRAME_MS)
      lastFrame.current = now
      const characters = Math.max(1, Math.round(elapsed * speed.current))
      setCount(stopAt(text, Math.min(target, shown + characters)))
    })
    return () => cancelAnimationFrame(frame)
  }, [active, shown, target, text])

  return { text: text.slice(0, shown), revealing: shown < target }
}
