import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { useIsTruncated } from './use-is-truncated'

// jsdom has no layout, so every element's widths are 0. The tests stub the two properties the hook
// reads, and capture the ResizeObserver the hook creates (the test setup's is a no-op) so a test can
// fire it by hand, as the browser would when the element's size changes.
const widths = { scrollWidth: 0, clientWidth: 0 }
const originals = {
  scrollWidth: Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollWidth'),
  clientWidth: Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientWidth'),
}
let observers: Array<{ callback: () => void; disconnected: boolean }> = []

beforeEach(() => {
  widths.scrollWidth = 0
  widths.clientWidth = 0
  Object.defineProperty(HTMLElement.prototype, 'scrollWidth', {
    configurable: true,
    get: () => widths.scrollWidth,
  })
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get: () => widths.clientWidth,
  })
  observers = []
  globalThis.ResizeObserver = class {
    entry = { callback: () => {}, disconnected: false }
    constructor(callback: () => void) {
      this.entry.callback = callback
      observers.push(this.entry)
    }
    observe() {}
    unobserve() {}
    disconnect() {
      this.entry.disconnected = true
    }
  } as unknown as typeof ResizeObserver
})

afterEach(() => {
  for (const key of ['scrollWidth', 'clientWidth'] as const) {
    if (originals[key]) Object.defineProperty(HTMLElement.prototype, key, originals[key])
    else delete (HTMLElement.prototype as unknown as Record<string, unknown>)[key]
  }
})

function Probe({ text = 'Department Lead, Apparel' }: { text?: string }) {
  const [ref, truncated] = useIsTruncated(text)
  return (
    <span ref={ref} data-testid="probe">
      {text}
      {truncated ? ' (cut)' : ''}
    </span>
  )
}

describe('useIsTruncated', () => {
  it('is true when the content is wider than the box', () => {
    widths.scrollWidth = 180
    widths.clientWidth = 120
    render(<Probe />)
    expect(screen.getByTestId('probe')).toHaveTextContent('(cut)')
  })

  it('is false when the content fits, including when the widths are equal', () => {
    widths.scrollWidth = 120
    widths.clientWidth = 120
    render(<Probe />)
    expect(screen.getByTestId('probe')).not.toHaveTextContent('(cut)')
  })

  it('updates when the element is resized', () => {
    widths.scrollWidth = 120
    widths.clientWidth = 120
    render(<Probe />)
    expect(screen.getByTestId('probe')).not.toHaveTextContent('(cut)')

    widths.clientWidth = 80
    act(() => observers.forEach((o) => o.callback()))
    expect(screen.getByTestId('probe')).toHaveTextContent('(cut)')

    widths.clientWidth = 200
    act(() => observers.forEach((o) => o.callback()))
    expect(screen.getByTestId('probe')).not.toHaveTextContent('(cut)')
  })

  it('checks again when the text it watches changes', () => {
    widths.scrollWidth = 100
    widths.clientWidth = 120
    const { rerender } = render(<Probe text="Short" />)
    expect(screen.getByTestId('probe')).not.toHaveTextContent('(cut)')
    widths.scrollWidth = 300
    rerender(<Probe text="A much longer title than before" />)
    expect(screen.getByTestId('probe')).toHaveTextContent('(cut)')
  })

  describe('when the web font arrives after the first check', () => {
    const original = Object.getOwnPropertyDescriptor(document, 'fonts')
    let resolveFonts: () => void = () => {}
    beforeEach(() => {
      const ready = new Promise<void>((resolve) => (resolveFonts = resolve))
      Object.defineProperty(document, 'fonts', { configurable: true, value: { ready } })
    })
    afterEach(() => {
      if (original) Object.defineProperty(document, 'fonts', original)
      else delete (document as unknown as Record<string, unknown>).fonts
    })

    it('checks again once document.fonts.ready resolves', async () => {
      widths.scrollWidth = 100
      widths.clientWidth = 120
      render(<Probe />)
      expect(screen.getByTestId('probe')).not.toHaveTextContent('(cut)')
      // The font's glyphs are wider, but the box didn't change, so no resize fires.
      widths.scrollWidth = 200
      await act(async () => resolveFonts())
      expect(screen.getByTestId('probe')).toHaveTextContent('(cut)')
    })

    it('ignores the font arriving after unmount', async () => {
      const { unmount } = render(<Probe />)
      const before = observers.length
      unmount()
      widths.scrollWidth = 999
      await act(async () => resolveFonts())
      // No error from setting state on a gone component, and no new observer.
      expect(observers).toHaveLength(before)
    })
  })

  it('stops observing when the element goes away', () => {
    const { unmount } = render(<Probe />)
    unmount()
    expect(observers.length).toBeGreaterThan(0)
    expect(observers.every((o) => o.disconnected)).toBe(true)
  })
})
