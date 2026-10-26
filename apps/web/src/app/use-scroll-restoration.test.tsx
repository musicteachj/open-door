import { useEffect } from 'react'
import { act, cleanup, render } from '@testing-library/react'
import { MemoryRouter, useNavigate } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useScrollRestoration } from './use-scroll-restoration'

// jsdom has no layout, so the window's scroll is a stub: scrollTo sets scrollY. The real thing is
// proved in a browser (e2e/directory-scroll.spec.ts).
let y = 0
let scrollTo: ReturnType<typeof vi.fn<(x: number, y: number) => void>>
const nav: { go: ReturnType<typeof useNavigate> | null } = { go: null }
const go: ReturnType<typeof useNavigate> = ((...args: Parameters<ReturnType<typeof useNavigate>>) =>
  nav.go!(...args)) as ReturnType<typeof useNavigate>

function Probe() {
  useScrollRestoration()
  const navigate = useNavigate()
  useEffect(() => {
    nav.go = navigate
  })
  return null
}

const scrollBy = (to: number) => {
  y = to
  window.dispatchEvent(new Event('scroll'))
}

beforeEach(() => {
  sessionStorage.clear()
  y = 0
  scrollTo = vi.fn<(x: number, y: number) => void>((_x, to) => {
    y = to
  })
  window.scrollTo = scrollTo as unknown as typeof window.scrollTo
  Object.defineProperty(window, 'scrollY', { configurable: true, get: () => y })
  render(
    <MemoryRouter initialEntries={['/directory']}>
      <Probe />
    </MemoryRouter>,
  )
})
afterEach(() => {
  vi.restoreAllMocks()
})

describe('scroll restoration', () => {
  it('starts a new page (a push) at the top', () => {
    scrollBy(500)
    act(() => void go('/directory?location=x'))
    expect(scrollTo).toHaveBeenLastCalledWith(0, 0)
  })

  it('puts Back where the visitor left that location', () => {
    scrollBy(500)
    act(() => void go('/directory?location=x'))
    scrollBy(120)
    act(() => void go(-1))
    expect(scrollTo).toHaveBeenLastCalledWith(0, 500)
    act(() => void go(1))
    expect(scrollTo).toHaveBeenLastCalledWith(0, 120)
  })

  it('keeps the position when the URL is replaced on the same page, as a search does', () => {
    scrollBy(300)
    act(() => void go('/directory?q=a', { replace: true }))
    expect(scrollTo).not.toHaveBeenCalled()
    expect(y).toBe(300)
  })

  it('keeps the position when a push is marked as opening a panel', () => {
    scrollBy(900)
    act(() => void go('/directory?source=CA-4.3~p2', { state: { keepScroll: true } }))
    expect(scrollTo).not.toHaveBeenCalled()
    expect(y).toBe(900)
    // Back closes it, and the page stays where the reader is.
    act(() => void go(-1))
    expect(scrollTo).not.toHaveBeenCalled()
  })

  it('keeps the position when Back or Forward moves between a marked entry and its page', () => {
    scrollBy(500)
    act(() => void go('/directory?source=CA-4.3~p2', { state: { keepScroll: true } }))
    // The reader scrolls on with the panel open (an answer kept streaming, say).
    scrollBy(1400)
    scrollTo.mockClear()
    act(() => void go(-1))
    // Closing is Back (a POP), but the page stays where the reader is, not where it was opened.
    expect(scrollTo).not.toHaveBeenCalled()
    expect(y).toBe(1400)
    // Forward reopens it: the marked entry is the one being returned to.
    act(() => void go(1))
    expect(scrollTo).not.toHaveBeenCalled()
    expect(y).toBe(1400)
  })

  it('keeps the position for a marked replace, as when another passage is shown', () => {
    scrollBy(700)
    act(() => void go('/directory?source=a', { state: { keepScroll: true } }))
    act(() => void go('/directory?source=b', { replace: true, state: { keepScroll: true } }))
    expect(scrollTo).not.toHaveBeenCalled()
    expect(y).toBe(700)
  })

  it('starts at the top for a marked replace that goes to another page', () => {
    scrollBy(700)
    act(() => void go('/ask', { replace: true, state: { keepScroll: true } }))
    expect(scrollTo).toHaveBeenLastCalledWith(0, 0)
  })

  it('starts at the top for a marked push to another page', () => {
    scrollBy(900)
    act(() => void go('/ask?source=CA-4.3~p2', { state: { keepScroll: true } }))
    expect(scrollTo).toHaveBeenLastCalledWith(0, 0)
  })

  it('does not treat a ?source= in the URL as a marker: an unmarked push still starts at the top', () => {
    scrollBy(900)
    act(() => void go('/directory?source=CA-4.3~p2'))
    expect(scrollTo).toHaveBeenLastCalledWith(0, 0)
  })

  it('still restores Back between unmarked entries of the same page', () => {
    scrollBy(500)
    act(() => void go('/directory?location=x&source=CA-4.3~p2'))
    scrollBy(120)
    act(() => void go(-1))
    expect(scrollTo).toHaveBeenLastCalledWith(0, 500)
  })

  it('starts at the top for an unmarked push on the same page, whatever else the URL holds', () => {
    scrollBy(900)
    act(() => void go('/directory?location=x'))
    expect(scrollTo).toHaveBeenLastCalledWith(0, 0)
  })

  it('starts at the top when a replace goes to another page', () => {
    scrollBy(300)
    act(() => void go('/ask', { replace: true }))
    expect(scrollTo).toHaveBeenLastCalledWith(0, 0)
  })

  it('does not touch the scroll on the first render', () => {
    expect(scrollTo).not.toHaveBeenCalled()
  })
})

describe('across a reload', () => {
  const entries = [
    { pathname: '/directory', key: 'first' },
    { pathname: '/directory/abc', key: 'second' },
  ]
  const mount = (initialIndex: number) =>
    render(
      <MemoryRouter initialEntries={entries} initialIndex={initialIndex}>
        <Probe />
      </MemoryRouter>,
    )

  it('keeps a saved position in sessionStorage, so Back after a reload still restores it', () => {
    cleanup() // the beforeEach's tree
    const first = mount(0)
    scrollBy(640)
    first.unmount() // the tab reloads: everything in memory is gone
    scrollTo.mockClear()
    y = 0

    mount(1)
    act(() => void go(-1))
    expect(scrollTo).toHaveBeenLastCalledWith(0, 640)
  })

  it('keeps only the last 50 positions', () => {
    cleanup()
    const first = mount(0)
    for (let i = 0; i < 60; i++) {
      scrollBy(i + 1)
      act(() => void go(i % 2 === 0 ? '/directory/abc' : '/directory'))
    }
    first.unmount()
    const stored = JSON.parse(sessionStorage.getItem('od.scrollPositions') ?? '[]') as unknown[]
    expect(stored.length).toBeGreaterThan(0)
    expect(stored.length).toBeLessThanOrEqual(50)
  })

  it('carries on when sessionStorage throws', () => {
    cleanup()
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError')
    })
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError')
    })
    const r = mount(0)
    scrollBy(200)
    act(() => void go('/directory/abc'))
    act(() => void go(-1))
    expect(scrollTo).toHaveBeenLastCalledWith(0, 200)
    r.unmount()
  })
})

describe('on the first render', () => {
  const mountAt = (key: string, saved: [string, number][]) => {
    cleanup() // its unmount saves the earlier tree's positions, so set ours after it
    sessionStorage.setItem('od.scrollPositions', JSON.stringify(saved))
    scrollTo.mockClear()
    y = 0
    render(
      <MemoryRouter initialEntries={[{ pathname: '/directory', key }]}>
        <Probe />
      </MemoryRouter>,
    )
  }

  it('restores a position saved for this history entry, as after a reload', () => {
    mountAt('abc', [['abc', 640]])
    expect(scrollTo).toHaveBeenLastCalledWith(0, 640)
  })

  it('leaves a fresh visit at the top: a new key with nothing saved', () => {
    mountAt('fresh', [['abc', 640]])
    expect(scrollTo).not.toHaveBeenCalled()
  })

  it('does not trust the "default" key, which every first visit to a tab has', () => {
    mountAt('default', [['default', 640]])
    expect(scrollTo).not.toHaveBeenCalled()
  })
})

describe('while a restore is cut short by a page that is not tall enough yet', () => {
  const entries = [
    { pathname: '/directory', key: 'first' },
    { pathname: '/directory/abc', key: 'second' },
  ]
  let ceiling = Infinity
  let grow: Array<() => void> = []

  const start = () => {
    cleanup()
    sessionStorage.setItem('od.scrollPositions', JSON.stringify([['first', 640]]))
    ceiling = 200
    grow = []
    globalThis.ResizeObserver = class {
      private readonly callback: () => void
      constructor(callback: () => void) {
        this.callback = callback
      }
      observe() {
        grow.push(this.callback)
      }
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver
    scrollTo = vi.fn<(x: number, y: number) => void>((_x, to) => {
      y = Math.min(to, ceiling)
    })
    window.scrollTo = scrollTo as unknown as typeof window.scrollTo
    y = 0
    render(
      <MemoryRouter initialEntries={entries} initialIndex={1}>
        <Probe />
      </MemoryRouter>,
    )
    act(() => void go(-1)) // Back to 'first': asks for 640, gets 200
    expect(y).toBe(200)
  }
  /** Leaves and comes back, which shows what is saved for 'first'. */
  const leaveAndReturn = () => {
    act(() => void go(1))
    scrollTo.mockClear()
    act(() => void go(-1))
  }

  it('keeps the saved position when the cut-short scroll is reported', () => {
    start()
    window.dispatchEvent(new Event('scroll')) // the browser reports the 200 it could reach
    leaveAndReturn()
    expect(scrollTo).toHaveBeenLastCalledWith(0, 640)
  })

  it('saves again once the restore has reached its position', () => {
    start()
    ceiling = Infinity
    act(() => grow.forEach((callback) => callback()))
    expect(y).toBe(640)
    scrollBy(700)
    leaveAndReturn()
    expect(scrollTo).toHaveBeenLastCalledWith(0, 700)
  })

  it('saves again as soon as the visitor scrolls', () => {
    start()
    window.dispatchEvent(new Event('wheel'))
    scrollBy(150)
    leaveAndReturn()
    expect(scrollTo).toHaveBeenLastCalledWith(0, 150)
  })
})
