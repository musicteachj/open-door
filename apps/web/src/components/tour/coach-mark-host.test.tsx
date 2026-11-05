import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CoachMarkHost } from './coach-mark-host'
import type { Rect } from './place-coach-mark'

function fakeRect({ x, y, width, height }: Rect): DOMRect {
  return {
    x,
    y,
    width,
    height,
    left: x,
    top: y,
    right: x + width,
    bottom: y + height,
    toJSON: () => ({}),
  }
}

function sized(el: HTMLElement, rect: Rect) {
  // Set on the element itself: the prototype's spy is shared by every element.
  el.getBoundingClientRect = () => fakeRect(rect)
  return el
}

function setViewport(width: number, height: number) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width })
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: height })
}

// jsdom lays nothing out, so every element is measured as this unless a test says otherwise.
const CARD_RECT = { x: 0, y: 0, width: 360, height: 200 }
beforeEach(() => {
  setViewport(1440, 900)
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(() =>
    fakeRect(CARD_RECT),
  )
  window.scrollBy = vi.fn<() => void>() as unknown as typeof window.scrollBy
})
afterEach(() => vi.restoreAllMocks())

const base = {
  step: 1,
  title: 'Ask a policy question',
  body: 'Ask about sick days.',
  chips: ['How many sick days do I get?'],
  onLeave: () => {},
}

function renderHost(
  target: HTMLElement | null,
  avoid: (HTMLElement | null)[] = [],
  props: Partial<React.ComponentProps<typeof CoachMarkHost>> = {},
) {
  return render(<CoachMarkHost target={target} avoid={avoid} {...base} {...props} />)
}

function element(rect: Rect) {
  const el = document.createElement('div')
  document.body.append(el)
  return sized(el, rect)
}

describe('CoachMarkHost', () => {
  it('rings the target and places the card 16 px below it', () => {
    const target = element({ x: 300, y: 200, width: 700, height: 56 })
    renderHost(target)
    expect(document.querySelector('[data-slot="tour-ring"]')).toHaveStyle({
      left: '296px',
      top: '196px',
      width: '708px',
      height: '64px',
    })
    expect(screen.getByRole('dialog')).toHaveStyle({ left: '470px', top: '272px' })
  })

  it('centers the card, with no ring, when the target is missing', () => {
    renderHost(null)
    expect(document.querySelector('[data-slot="tour-ring"]')).toBeNull()
    expect(screen.getByRole('dialog')).toHaveStyle({ left: '540px', top: '350px' })
  })

  it('keeps the card off the elements to avoid', () => {
    const target = element({ x: 300, y: 400, width: 700, height: 56 })
    const below = element({ x: 300, y: 472, width: 700, height: 100 })
    renderHost(target, [below])
    // Below would cover it, so the card goes above: 400 - 16 - 200.
    expect(screen.getByRole('dialog')).toHaveStyle({ top: '184px' })
  })

  it('places again when the window is resized', () => {
    const target = element({ x: 300, y: 200, width: 700, height: 56 })
    renderHost(target)
    expect(screen.getByRole('dialog')).toHaveStyle({ left: '470px' })
    sized(target, { x: 100, y: 200, width: 700, height: 56 })
    act(() => {
      window.dispatchEvent(new Event('resize'))
    })
    expect(screen.getByRole('dialog')).toHaveStyle({ left: '270px' })
  })

  it('places again when anything scrolls', () => {
    const target = element({ x: 300, y: 200, width: 700, height: 56 })
    renderHost(target)
    sized(target, { x: 300, y: 100, width: 700, height: 56 })
    act(() => {
      document.dispatchEvent(new Event('scroll'))
    })
    expect(screen.getByRole('dialog')).toHaveStyle({ top: '172px' })
  })

  it('stops listening when it unmounts', () => {
    const spy = vi.spyOn(window, 'removeEventListener')
    const { unmount } = renderHost(element({ x: 300, y: 200, width: 700, height: 56 }))
    unmount()
    expect(spy).toHaveBeenCalledWith('resize', expect.any(Function))
  })

  describe('on a phone', () => {
    beforeEach(() => setViewport(390, 844))

    it('docks as a sheet and scrolls the page so the target sits above it', () => {
      // The sheet is 200 px tall, so it starts at 644; the target ends at 700 and needs 716.
      const target = element({ x: 16, y: 644, width: 358, height: 56 })
      renderHost(target)
      expect(screen.getByRole('dialog')).toHaveClass('fixed', 'bottom-0')
      expect(window.scrollBy).toHaveBeenCalledWith({ top: 72, left: 0, behavior: 'instant' })
    })

    it('does not scroll when the target is already clear of the sheet', () => {
      renderHost(element({ x: 16, y: 300, width: 358, height: 56 }))
      expect(window.scrollBy).not.toHaveBeenCalled()
    })

    it('scrolls once for a step, not on every scroll the visitor makes', () => {
      const target = element({ x: 16, y: 644, width: 358, height: 56 })
      renderHost(target)
      act(() => {
        document.dispatchEvent(new Event('scroll'))
      })
      expect(window.scrollBy).toHaveBeenCalledTimes(1)
    })
  })

  describe('focus', () => {
    // Closes itself when the visitor leaves, as the real owner of the host does.
    function Closing(props: Partial<React.ComponentProps<typeof CoachMarkHost>>) {
      const [open, setOpen] = useState(true)
      const target = useState(() => element({ x: 300, y: 200, width: 700, height: 56 }))[0]
      return open ? (
        <CoachMarkHost target={target} {...base} {...props} onLeave={() => setOpen(false)} />
      ) : null
    }

    function Harness() {
      const [open, setOpen] = useState(false)
      const [target, setTarget] = useState<HTMLElement | null>(null)
      return (
        <>
          <textarea
            aria-label="Message"
            ref={(el) => {
              if (el && target !== el)
                setTarget(sized(el, { x: 300, y: 200, width: 700, height: 56 }))
            }}
          />
          <button onClick={() => setOpen(true)}>Start</button>
          {open && (
            <CoachMarkHost target={target} avoid={[]} {...base} onLeave={() => setOpen(false)} />
          )}
        </>
      )
    }

    it('returns to the element that had focus before it opened when the visitor leaves', async () => {
      const user = userEvent.setup()
      render(<Harness />)
      await user.click(screen.getByRole('button', { name: 'Start' }))
      expect(screen.getByRole('heading', { level: 2 })).toHaveFocus()
      await user.click(screen.getByRole('button', { name: 'Leave the tour' }))
      expect(screen.queryByRole('dialog')).toBeNull()
      expect(screen.getByRole('button', { name: 'Start' })).toHaveFocus()
    })

    it('returns on Escape too', async () => {
      const user = userEvent.setup()
      render(<Harness />)
      screen.getByRole('textbox').focus()
      await user.keyboard('{Tab}{Enter}')
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      await user.keyboard('{Escape}')
      expect(screen.queryByRole('dialog')).toBeNull()
      expect(screen.getByRole('button', { name: 'Start' })).toHaveFocus()
    })

    it('does not pull focus back when it unmounts for another reason', () => {
      const before = document.createElement('button')
      const other = document.createElement('button')
      document.body.append(before, other)
      before.focus()
      const { unmount } = renderHost(element({ x: 300, y: 200, width: 700, height: 56 }))
      other.focus()
      unmount()
      expect(other).toHaveFocus()
    })

    it('returns to fallbackFocus when what had focus before is gone', async () => {
      const user = userEvent.setup()
      const fallback = document.createElement('button')
      document.body.append(fallback)
      const before = document.createElement('button')
      document.body.append(before)
      before.focus()
      render(<Closing fallbackFocus={() => fallback} />)
      before.remove()
      await user.click(screen.getByRole('button', { name: 'Leave the tour' }))
      expect(fallback).toHaveFocus()
    })

    it('ignores a page region the app focused (tabindex -1) and uses fallbackFocus instead', async () => {
      const region = document.createElement('main')
      region.tabIndex = -1
      const fallback = document.createElement('button')
      document.body.append(region, fallback)
      region.focus()
      const user = userEvent.setup()
      render(<Closing fallbackFocus={() => fallback} />)
      await user.click(screen.getByRole('button', { name: 'Leave the tour' }))
      expect(fallback).toHaveFocus()
      region.remove()
      fallback.remove()
    })

    it('prefers what had focus before to fallbackFocus when it is still there', async () => {
      const user = userEvent.setup()
      const fallback = document.createElement('button')
      const before = document.createElement('button')
      document.body.append(fallback, before)
      before.focus()
      render(<Closing fallbackFocus={() => fallback} />)
      await user.click(screen.getByRole('button', { name: 'Leave the tour' }))
      expect(before).toHaveFocus()
    })
  })

  describe('cleanup and later-mounting elements', () => {
    it('removes the scroll listener on unmount', () => {
      const spy = vi.spyOn(document, 'removeEventListener')
      const { unmount } = renderHost(element({ x: 300, y: 200, width: 700, height: 56 }))
      unmount()
      expect(spy).toHaveBeenCalledWith('scroll', expect.any(Function), expect.anything())
    })

    describe('with a ResizeObserver', () => {
      const observed: Element[] = []
      const disconnect = vi.fn<() => void>()
      beforeEach(() => {
        observed.length = 0
        disconnect.mockClear()
        vi.stubGlobal(
          'ResizeObserver',
          class {
            observe(el: Element) {
              observed.push(el)
            }
            unobserve() {}
            disconnect = disconnect
          },
        )
      })
      afterEach(() => vi.unstubAllGlobals())

      it('disconnects on unmount', () => {
        const { unmount } = renderHost(element({ x: 300, y: 200, width: 700, height: 56 }))
        expect(disconnect).not.toHaveBeenCalled()
        unmount()
        expect(disconnect).toHaveBeenCalled()
      })

      it('observes an element to avoid that mounts after the host', () => {
        const target = element({ x: 300, y: 200, width: 700, height: 56 })
        const { rerender } = renderHost(target, [null])
        const late = element({ x: 300, y: 300, width: 700, height: 100 })
        expect(observed).not.toContain(late)
        rerender(<CoachMarkHost target={target} avoid={[late]} {...base} />)
        expect(observed).toContain(late)
      })
    })
  })

  describe('on a desktop, after the first measure needed no scroll', () => {
    it('does not scroll when the visitor later scrolls the target out of view', () => {
      const target = element({ x: 100, y: 100, width: 300, height: 40 })
      renderHost(target)
      expect(window.scrollBy).not.toHaveBeenCalled()
      sized(target, { x: 100, y: 1200, width: 300, height: 40 })
      act(() => {
        document.dispatchEvent(new Event('scroll'))
      })
      expect(window.scrollBy).not.toHaveBeenCalled()
    })
  })

  describe('with a sticky header over the page', () => {
    it('scrolls a target hidden under the header it is given into view', () => {
      const header = element({ x: 0, y: 0, width: 1440, height: 150 })
      renderHost(element({ x: 100, y: 100, width: 300, height: 40 }), [], { header })
      expect(window.scrollBy).toHaveBeenCalledTimes(1)
    })

    it('holds no knowledge of any page’s header: without one given, the same target is in view', () => {
      const stray = document.createElement('div')
      stray.dataset.slot = 'conversation-header'
      document.body.append(stray, element({ x: 0, y: 0, width: 1440, height: 150 }))
      renderHost(element({ x: 100, y: 100, width: 300, height: 40 }))
      expect(window.scrollBy).not.toHaveBeenCalled()
      stray.remove()
    })
  })

  describe('on a phone, above the top of the screen', () => {
    beforeEach(() => setViewport(390, 844))
    it('scrolls back up so the target sits 16 px from the top', () => {
      renderHost(element({ x: 16, y: -200, width: 358, height: 56 }))
      expect(window.scrollBy).toHaveBeenCalledWith({ top: -216, left: 0, behavior: 'instant' })
    })
  })
})
