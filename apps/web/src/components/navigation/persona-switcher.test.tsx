import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { act } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PersonaSwitcher } from './persona-switcher'

// Whether the title is cut off is the browser's to say, so the tests stub the widths the hook reads.
const widths = { scrollWidth: 100, clientWidth: 100 }
const originals = {
  scrollWidth: Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollWidth'),
  clientWidth: Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientWidth'),
}
beforeEach(() => {
  Object.defineProperty(HTMLElement.prototype, 'scrollWidth', {
    configurable: true,
    get: () => widths.scrollWidth,
  })
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get: () => widths.clientWidth,
  })
})
afterEach(() => {
  widths.scrollWidth = 100
  widths.clientWidth = 100
  for (const key of ['scrollWidth', 'clientWidth'] as const) {
    if (originals[key]) Object.defineProperty(HTMLElement.prototype, key, originals[key])
    else delete (HTMLElement.prototype as unknown as Record<string, unknown>)[key]
  }
})

const TITLE = 'Department Lead, Apparel'

describe('PersonaSwitcher', () => {
  it('is named for the person and the full title', () => {
    render(<PersonaSwitcher name="Priya Raman" title={TITLE} />)
    expect(screen.getByRole('button')).toHaveAccessibleName(
      'Priya Raman, Department Lead, Apparel. Current persona. Switch persona',
    )
  })

  it('keeps the full title in its name when the title is cut off', () => {
    widths.scrollWidth = 300
    render(<PersonaSwitcher name="Priya Raman" title={TITLE} />)
    expect(screen.getByRole('button')).toHaveAccessibleName(
      'Priya Raman, Department Lead, Apparel. Current persona. Switch persona',
    )
  })

  it('shows the name, the title, and the initials', () => {
    render(<PersonaSwitcher name="Priya Raman" title={TITLE} />)
    const button = screen.getByRole('button')
    expect(button).toHaveTextContent('Priya Raman')
    expect(button).toHaveTextContent(TITLE)
    expect(button).toHaveTextContent('PR')
  })

  it('shows a tooltip with the full title when the title is truncated', async () => {
    widths.scrollWidth = 300
    const user = userEvent.setup()
    render(<PersonaSwitcher name="Priya Raman" title={TITLE} />)
    await user.tab()
    expect(await screen.findByRole('tooltip')).toHaveTextContent(TITLE)
  })

  it('shows the tooltip for a focused switcher that only then becomes truncated', async () => {
    const callbacks: Array<() => void> = []
    globalThis.ResizeObserver = class {
      constructor(callback: () => void) {
        callbacks.push(callback)
      }
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
    const warns = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const user = userEvent.setup()
    render(<PersonaSwitcher name="Priya Raman" title={TITLE} />)
    await user.tab()
    expect(screen.getByRole('button')).toHaveFocus()
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()

    widths.scrollWidth = 300
    act(() => callbacks.forEach((callback) => callback()))
    // No refocusing: the focus that was already there is enough.
    expect(await screen.findByRole('tooltip')).toHaveTextContent(TITLE)

    const messages = [...errors.mock.calls, ...warns.mock.calls].map((call) => String(call[0]))
    expect(messages.filter((m) => /controlled|uncontrolled/i.test(m))).toEqual([])
    errors.mockRestore()
    warns.mockRestore()
  })

  it('shows no tooltip when the title fits', async () => {
    const user = userEvent.setup()
    render(<PersonaSwitcher name="Priya Raman" title={TITLE} />)
    await user.tab()
    expect(screen.getByRole('button')).toHaveFocus()
    await user.hover(screen.getByRole('button'))
    // Past the 300 ms hover delay, so a tooltip that was going to show would be there.
    await new Promise((resolve) => setTimeout(resolve, 450))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('shows the spinner and the busy label on one line, and says it is busy', () => {
    render(<PersonaSwitcher name="Priya Raman" title={TITLE} busyLabel="Switching to Marcus…" />)
    const button = screen.getByRole('button')
    expect(button).toHaveAccessibleName('Switching to Marcus…')
    expect(button).toHaveAttribute('aria-busy', 'true')
    const label = screen.getByText('Switching to Marcus…')
    expect(label).toHaveClass('truncate')
    expect(button.querySelector('svg.animate-spin')).toHaveAttribute('aria-hidden', 'true')
    expect(label.parentElement).toBe(button)
  })

  it('does not show the person while busy', () => {
    render(<PersonaSwitcher name="Priya Raman" title={TITLE} busyLabel="Switching to Marcus…" />)
    expect(screen.queryByText(TITLE)).not.toBeInTheDocument()
  })

  it('treats an empty busyLabel as busy, the same as the menu does', () => {
    render(<PersonaSwitcher name="Priya Raman" title={TITLE} busyLabel="" />)
    const button = screen.getByRole('button')
    expect(button).toHaveAttribute('aria-busy', 'true')
    expect(screen.queryByText(TITLE)).not.toBeInTheDocument()
  })

  it('is aria-disabled while busy, and not otherwise', () => {
    const { rerender } = render(<PersonaSwitcher name="Priya Raman" title={TITLE} />)
    expect(screen.getByRole('button')).not.toHaveAttribute('aria-disabled')
    rerender(<PersonaSwitcher name="Priya Raman" title={TITLE} busyLabel="Switching…" />)
    expect(screen.getByRole('button')).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('button')).toHaveClass('aria-disabled:cursor-default')
  })

  it('is not busy by default', () => {
    render(<PersonaSwitcher name="Priya Raman" title={TITLE} />)
    expect(screen.getByRole('button')).not.toHaveAttribute('aria-busy', 'true')
  })

  it('passes clicks and other button props through', async () => {
    const user = userEvent.setup()
    let clicks = 0
    render(
      <PersonaSwitcher name="Priya Raman" title={TITLE} onClick={() => (clicks += 1)} id="who" />,
    )
    await user.click(screen.getByRole('button'))
    expect(clicks).toBe(1)
    expect(screen.getByRole('button')).toHaveAttribute('id', 'who')
  })
})
