import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { BottomSheet, SheetTitle } from './bottom-sheet'

function setup(onClose = vi.fn<() => void>()) {
  render(
    <>
      <button>Behind</button>
      <BottomSheet onClose={onClose}>
        <header>
          <SheetTitle>Sick leave</SheetTitle>
          <button>Inside one</button>
        </header>
        <div data-testid="body">
          <button>Inside two</button>
        </div>
      </BottomSheet>
    </>,
  )
  return onClose
}

const handle = () => document.querySelector<HTMLElement>('[data-slot="bottom-sheet-handle"]')!

describe('BottomSheet', () => {
  it('is a modal dialog named by its visible title, and hides the page behind it', () => {
    setup()
    expect(screen.getByRole('dialog', { name: 'Sick leave' })).toBeInTheDocument()
    // The page's own button is not reachable by role while the dialog is modal.
    expect(screen.queryByRole('button', { name: 'Behind' })).not.toBeInTheDocument()
  })

  it('is named by the title it holds, and by nothing else', () => {
    setup()
    const dialog = screen.getByRole('dialog')
    expect(dialog).not.toHaveAttribute('aria-label')
    const title = screen.getByRole('heading', { name: 'Sick leave' })
    expect(dialog.getAttribute('aria-labelledby')).toBe(title.id)
    expect(screen.getAllByRole('heading')).toHaveLength(1)
  })

  it('keeps Tab inside, wrapping from the last control to the first', async () => {
    setup()
    const user = userEvent.setup()
    screen.getByRole('button', { name: 'Inside two' }).focus()
    await user.tab()
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Inside one' }))
    expect(document.activeElement?.closest('[role="dialog"]')).not.toBeNull()
  })

  it('closes on Escape', async () => {
    const onClose = setup()
    await userEvent.setup().keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('closes when the overlay is pressed', async () => {
    const onClose = setup()
    const overlay = document.querySelector('[data-slot="bottom-sheet-overlay"]')!
    await userEvent.setup().pointer({ keys: '[MouseLeft]', target: overlay })
    expect(onClose).toHaveBeenCalled()
  })

  it('closes when the handle is dragged down past the threshold and released', () => {
    const onClose = setup()
    fireEvent.pointerDown(handle(), { clientY: 100, pointerId: 1, button: 0 })
    fireEvent.pointerMove(handle(), { clientY: 150, pointerId: 1 })
    expect(screen.getByRole('dialog').style.transform).toBe('translateY(50px)')
    fireEvent.pointerMove(handle(), { clientY: 230, pointerId: 1 })
    fireEvent.pointerUp(handle(), { clientY: 230, pointerId: 1 })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('springs back and stays open for a short drag, an upward drag, or a canceled one', () => {
    const onClose = setup()
    fireEvent.pointerDown(handle(), { clientY: 100, pointerId: 1, button: 0 })
    fireEvent.pointerMove(handle(), { clientY: 150, pointerId: 1 })
    fireEvent.pointerUp(handle(), { clientY: 150, pointerId: 1 })
    expect(screen.getByRole('dialog').style.transform).toBe('')
    fireEvent.pointerDown(handle(), { clientY: 100, pointerId: 1, button: 0 })
    fireEvent.pointerMove(handle(), { clientY: 20, pointerId: 1 })
    expect(screen.getByRole('dialog').style.transform).toBe('')
    fireEvent.pointerUp(handle(), { clientY: 20, pointerId: 1 })
    fireEvent.pointerDown(handle(), { clientY: 100, pointerId: 1, button: 0 })
    fireEvent.pointerMove(handle(), { clientY: 300, pointerId: 1 })
    fireEvent.pointerCancel(handle(), { clientY: 300, pointerId: 1 })
    expect(onClose).not.toHaveBeenCalled()
  })

  it('moves only for the pointer that started the drag', () => {
    const onClose = setup()
    fireEvent.pointerDown(handle(), { clientY: 100, pointerId: 1, button: 0 })
    fireEvent.pointerUp(handle(), { clientY: 400, pointerId: 2 })
    expect(onClose).not.toHaveBeenCalled()
  })

  describe('the swipe starts from the header too, but not from the body', () => {
    const grab = (target: Element) => {
      fireEvent.pointerDown(target, { clientY: 100, pointerId: 1, button: 0 })
      fireEvent.pointerMove(target, { clientY: 260, pointerId: 1 })
      fireEvent.pointerUp(target, { clientY: 260, pointerId: 1 })
    }

    it('closes from a drag that starts on the header', () => {
      const onClose = setup()
      grab(screen.getByRole('heading', { name: 'Sick leave' }))
      expect(onClose).toHaveBeenCalledTimes(1)
    })

    it('does not close from a drag that starts in the body, which scrolls', () => {
      const onClose = setup()
      grab(screen.getByTestId('body'))
      expect(onClose).not.toHaveBeenCalled()
      expect(screen.getByRole('dialog').style.transform).toBe('')
    })

    it('does not start a drag on a control in the header', () => {
      const onClose = setup()
      grab(screen.getByRole('button', { name: 'Inside one' }))
      expect(onClose).not.toHaveBeenCalled()
    })

    it('keeps the header from scrolling the page on a touch', () => {
      setup()
      expect(screen.getByTestId('body').parentElement).toHaveClass('[&_header]:touch-none')
    })
  })
})
