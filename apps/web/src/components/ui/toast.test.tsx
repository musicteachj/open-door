import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Toast, ToastProvider, ToastViewport } from './toast'

function renderToast(props: Partial<React.ComponentProps<typeof Toast>> = {}) {
  return render(
    <ToastProvider>
      <Toast defaultOpen {...props}>
        Now viewing as Marcus Bell.
      </Toast>
      <ToastViewport />
    </ToastProvider>,
  )
}

// The message appears twice in the page: once in the toast, once in Radix's screen-reader
// announcement. These look only at the toast itself, which is a list item in the viewport.
const toast = () => screen.queryByRole('listitem')
// Radix listens for the pointer on the region, and the list inside it carries our classes.
const region = () => screen.getByRole('region')
const list = () => screen.getByRole('list')

describe('Toast', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows its message with a polite status', () => {
    renderToast()
    expect(toast()).toHaveTextContent('Now viewing as Marcus Bell.')
    expect(screen.getAllByRole('status').length).toBeGreaterThan(0)
  })

  it('has the design’s surface and a success icon by default', () => {
    renderToast()
    expect(toast()).toHaveClass(
      'bg-surface-raised',
      'border-border',
      'rounded-md',
      'shadow-md',
      'min-w-80',
    )
    expect(toast()?.querySelector('[data-slot="toast-icon"]')).toHaveClass('text-success')
  })

  it('has an info tone', () => {
    renderToast({ tone: 'info' })
    expect(toast()?.querySelector('[data-slot="toast-icon"]')).toHaveClass('text-ink-muted')
  })

  it('reads at regular weight, and shows the focus ring when the viewport is focused', () => {
    renderToast()
    expect(screen.getByText('Now viewing as Marcus Bell.', { selector: 'div' })).toHaveClass(
      'font-regular',
    )
    expect(list()).not.toHaveClass('outline-none')
  })

  it('sits in the bottom-right corner', () => {
    renderToast()
    expect(list()).toHaveClass('fixed', 'bottom-6', 'right-6')
  })

  it('closes by itself after 6 seconds by default', () => {
    renderToast()
    act(() => void vi.advanceTimersByTime(5900))
    expect(toast()).toBeInTheDocument()
    act(() => void vi.advanceTimersByTime(200))
    expect(toast()).not.toBeInTheDocument()
  })

  it('closes after the duration it is given', () => {
    renderToast({ duration: 2000 })
    act(() => void vi.advanceTimersByTime(1900))
    expect(toast()).toBeInTheDocument()
    act(() => void vi.advanceTimersByTime(200))
    expect(toast()).not.toBeInTheDocument()
  })

  it('tells its owner when it closes', () => {
    const onOpenChange = vi.fn<(open: boolean) => void>()
    renderToast({ duration: 1000, onOpenChange })
    act(() => void vi.advanceTimersByTime(1100))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('closes with its Dismiss button', async () => {
    // Testing Library's async wrapper waits on a real setTimeout unless Jest's fake timers are
    // detected, which hangs under Vitest's. Nothing in this test needs the clock, so it runs on
    // the real one.
    vi.useRealTimers()
    const user = userEvent.setup()
    renderToast()
    await user.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(toast()).not.toBeInTheDocument()
  })

  describe('pausing', () => {
    it('pauses while the pointer is over it, and resumes with what was left', () => {
      renderToast({ duration: 4000 })
      act(() => void vi.advanceTimersByTime(3000))
      fireEvent.pointerMove(region())
      act(() => void vi.advanceTimersByTime(60_000))
      expect(toast()).toBeInTheDocument()
      fireEvent.pointerLeave(region())
      act(() => void vi.advanceTimersByTime(900))
      expect(toast()).toBeInTheDocument()
      act(() => void vi.advanceTimersByTime(200))
      expect(toast()).not.toBeInTheDocument()
    })

    it('pauses while focus is inside, and resumes when focus leaves', () => {
      renderToast({ duration: 4000 })
      const dismiss = screen.getByRole('button', { name: 'Dismiss' })
      act(() => dismiss.focus())
      act(() => void vi.advanceTimersByTime(60_000))
      expect(toast()).toBeInTheDocument()
      act(() => dismiss.blur())
      act(() => void vi.advanceTimersByTime(4100))
      expect(toast()).not.toBeInTheDocument()
    })

    it('stays paused when the pointer leaves but focus is still inside', () => {
      renderToast({ duration: 4000 })
      const dismiss = screen.getByRole('button', { name: 'Dismiss' })
      act(() => dismiss.focus())
      fireEvent.pointerMove(region())
      fireEvent.pointerLeave(region())
      act(() => void vi.advanceTimersByTime(60_000))
      expect(toast()).toBeInTheDocument()
    })

    it('pauses while the window is blurred, and resumes when it is focused again', () => {
      renderToast({ duration: 4000 })
      fireEvent.blur(window)
      act(() => void vi.advanceTimersByTime(60_000))
      expect(toast()).toBeInTheDocument()
      fireEvent.focus(window)
      act(() => void vi.advanceTimersByTime(4100))
      expect(toast()).not.toBeInTheDocument()
    })
  })
})
