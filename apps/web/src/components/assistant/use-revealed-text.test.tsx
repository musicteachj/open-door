import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { stubMediaQuery } from '@/test/media-query'
import { useRevealedText } from './use-revealed-text'

// A hand-driven requestAnimationFrame: `frame(ms)` moves the clock and runs what was queued.
let now = 0
let queued = new Map<number, FrameRequestCallback>()
let nextId = 1
function frame(ms = 16) {
  now += ms
  const callbacks = [...queued.values()]
  queued = new Map()
  act(() => {
    for (const callback of callbacks) callback(now)
  })
}
function frames(count: number, ms = 16) {
  for (let i = 0; i < count; i++) frame(ms)
}

beforeEach(() => {
  now = 0
  queued = new Map()
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    const id = nextId++
    queued.set(id, callback)
    return id
  })
  vi.stubGlobal('cancelAnimationFrame', (id: number) => queued.delete(id))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

const LONG = 'word '.repeat(300).trim()

describe('useRevealedText', () => {
  it('plays a large piece out over several frames, all of it within about half a second', () => {
    stubMediaQuery(true)
    const { result, rerender } = renderHook(
      ({ text, streaming }) => useRevealedText(text, streaming),
      {
        initialProps: { text: '', streaming: true },
      },
    )
    rerender({ text: LONG, streaming: true })
    expect(result.current.text).toBe('')
    expect(result.current.revealing).toBe(true)
    frames(5)
    const partway = result.current.text.length
    expect(partway).toBeGreaterThan(0)
    expect(partway).toBeLessThan(LONG.length)
    expect(LONG.startsWith(result.current.text)).toBe(true)
    // Words appear whole: the revealed part ends at a space or the end.
    expect(LONG[partway] === ' ' || partway === LONG.length).toBe(true)
    frames(40)
    expect(result.current.text).toBe(LONG)
    expect(result.current.revealing).toBe(false)
  })

  it('shows a short piece at once, as ordinary streaming arrives', () => {
    stubMediaQuery(true)
    const { result, rerender } = renderHook(
      ({ text, streaming }) => useRevealedText(text, streaming),
      { initialProps: { text: '', streaming: true } },
    )
    rerender({ text: 'You get five days', streaming: true })
    expect(result.current).toEqual({ text: 'You get five days', revealing: false })
    rerender({ text: 'You get five days of sick leave.', streaming: true })
    expect(result.current).toEqual({ text: 'You get five days of sick leave.', revealing: false })
  })

  it('finishes the reveal after the stream ends', () => {
    stubMediaQuery(true)
    const { result, rerender } = renderHook(
      ({ text, streaming }) => useRevealedText(text, streaming),
      {
        initialProps: { text: '', streaming: true },
      },
    )
    rerender({ text: LONG, streaming: false })
    expect(result.current.revealing).toBe(true)
    frames(45)
    expect(result.current.text).toBe(LONG)
    expect(result.current.revealing).toBe(false)
  })

  it('starts over from nothing when the text is taken back and replaced', () => {
    stubMediaQuery(true)
    const { result, rerender } = renderHook(
      ({ text, streaming }) => useRevealedText(text, streaming),
      {
        initialProps: { text: 'A working note about the search', streaming: true },
      },
    )
    frames(45)
    expect(result.current.text).toBe('A working note about the search')
    rerender({ text: '', streaming: true })
    expect(result.current.text).toBe('')
    rerender({ text: LONG, streaming: true })
    expect(result.current.text).toBe('')
    frame()
    frame()
    expect(result.current.text.length).toBeLessThan(LONG.length)
  })

  it('paces a replacement from nothing even when it is only a little longer than what was shown', () => {
    stubMediaQuery(true)
    const first = 'x'.repeat(100)
    const { result, rerender } = renderHook(
      ({ text, streaming }) => useRevealedText(text, streaming),
      { initialProps: { text: first, streaming: true } },
    )
    // Taken back and replaced in one render: 130 characters that don't continue the 100 shown.
    rerender({ text: 'y '.repeat(65), streaming: true })
    expect(result.current.text).toBe('')
    expect(result.current.revealing).toBe(true)
  })

  it('shows a finished answer whole, with nothing paced', () => {
    stubMediaQuery(true)
    const { result } = renderHook(() => useRevealedText(LONG, false))
    expect(result.current).toEqual({ text: LONG, revealing: false })
  })

  it('shows text that is already there when it mounts mid-stream, and paces only what follows', () => {
    stubMediaQuery(true)
    const { result, rerender } = renderHook(
      ({ text, streaming }) => useRevealedText(text, streaming),
      { initialProps: { text: 'Already shown.', streaming: true } },
    )
    expect(result.current).toEqual({ text: 'Already shown.', revealing: false })
    rerender({ text: `Already shown. ${LONG}`, streaming: true })
    expect(result.current.text).toBe('Already shown.')
    expect(result.current.revealing).toBe(true)
  })

  it('shows text as it arrives under reduced motion', () => {
    stubMediaQuery(false)
    const { result, rerender } = renderHook(
      ({ text, streaming }) => useRevealedText(text, streaming),
      {
        initialProps: { text: '', streaming: true },
      },
    )
    rerender({ text: LONG, streaming: true })
    expect(result.current).toEqual({ text: LONG, revealing: false })
  })

  it('keeps showing what arrived under reduced motion when motion is allowed again', () => {
    const media = stubMediaQuery(false)
    const { result, rerender } = renderHook(
      ({ text, streaming }) => useRevealedText(text, streaming),
      { initialProps: { text: '', streaming: true } },
    )
    rerender({ text: LONG, streaming: true })
    expect(result.current.text).toBe(LONG)
    act(() => media.set(true))
    expect(result.current).toEqual({ text: LONG, revealing: false })
  })

  it('shows the whole text at once when the answer is settled (stopped or failed)', () => {
    stubMediaQuery(true)
    const { result, rerender } = renderHook(
      ({ text, streaming, settled }) => useRevealedText(text, streaming, settled),
      { initialProps: { text: '', streaming: true, settled: false } },
    )
    rerender({ text: LONG, streaming: true, settled: false })
    frame()
    expect(result.current.revealing).toBe(true)
    rerender({ text: LONG, streaming: false, settled: true })
    expect(result.current).toEqual({ text: LONG, revealing: false })
  })

  it('carries a reveal on when another component takes the same turn over', () => {
    stubMediaQuery(true)
    const live = renderHook(
      ({ text, streaming }) => useRevealedText(text, streaming, false, 'turn-1'),
      { initialProps: { text: '', streaming: true } },
    )
    live.rerender({ text: LONG, streaming: false })
    frames(3)
    const partway = live.result.current.text.length
    expect(partway).toBeGreaterThan(0)
    expect(partway).toBeLessThan(LONG.length)
    // The saved copy takes the turn over (a new component), while the reveal is still going.
    const saved = renderHook(() => useRevealedText(LONG, false, false, 'turn-1'))
    live.unmount()
    expect(saved.result.current.text.length).toBe(partway)
    expect(saved.result.current.revealing).toBe(true)
    frames(45)
    expect(saved.result.current).toEqual({ text: LONG, revealing: false })
    // Once done, nothing is carried: the turn drawn again later shows whole.
    const later = renderHook(() => useRevealedText(LONG, false, false, 'turn-1'))
    expect(later.result.current).toEqual({ text: LONG, revealing: false })
  })

  it('never splits a surrogate pair', () => {
    stubMediaQuery(true)
    const text = '😀'.repeat(400)
    const { result, rerender } = renderHook(
      ({ text, streaming }) => useRevealedText(text, streaming),
      {
        initialProps: { text: '', streaming: true },
      },
    )
    rerender({ text, streaming: true })
    for (let i = 0; i < 10; i++) {
      frame()
      expect(result.current.text.length % 2).toBe(0)
    }
  })
})
