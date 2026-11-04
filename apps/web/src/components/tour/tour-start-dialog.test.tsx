import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { TourStartDialog } from './tour-start-dialog'

function setup() {
  const onOpenChange = vi.fn<() => void>()
  const onStart = vi.fn<() => void>()
  render(<TourStartDialog open onOpenChange={onOpenChange} onStart={onStart} />)
  return { onOpenChange, onStart, user: userEvent.setup() }
}

describe('TourStartDialog', () => {
  it('is an alert dialog with the title and the sandbox sentence', () => {
    setup()
    const dialog = screen.getByRole('alertdialog', { name: 'Start the tour?' })
    expect(dialog).toHaveAccessibleDescription(
      'The tour starts a new sandbox as Priya Raman. Your current sandbox stays until it expires.',
    )
  })

  it('focuses Cancel first', () => {
    setup()
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus()
  })

  it('puts Cancel before "Start the tour" in the tab order', async () => {
    const { user } = setup()
    await user.tab()
    expect(screen.getByRole('button', { name: 'Start the tour' })).toHaveFocus()
    const cancel = screen.getByRole('button', { name: 'Cancel' })
    const start = screen.getByRole('button', { name: 'Start the tour' })
    expect(cancel.compareDocumentPosition(start) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('cancels from the button and from Escape', async () => {
    const { user, onOpenChange } = setup()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onOpenChange).toHaveBeenLastCalledWith(false)
    await user.keyboard('{Escape}')
    expect(onOpenChange).toHaveBeenCalledTimes(2)
  })

  it('starts from the primary button without closing itself', async () => {
    const { user, onStart, onOpenChange } = setup()
    await user.click(screen.getByRole('button', { name: 'Start the tour' }))
    expect(onStart).toHaveBeenCalledTimes(1)
    expect(onOpenChange).not.toHaveBeenCalled()
  })

  describe('while starting', () => {
    function starting() {
      const onOpenChange = vi.fn<() => void>()
      const onStart = vi.fn<() => void>()
      render(<TourStartDialog open starting onOpenChange={onOpenChange} onStart={onStart} />)
      return { onOpenChange, onStart, user: userEvent.setup() }
    }

    it('ignores a second press, shows the busy pattern, and holds Cancel and Escape', async () => {
      const { user, onStart, onOpenChange } = starting()
      const start = screen.getByRole('button', { name: 'Start the tour' })
      expect(start).toHaveAttribute('aria-busy', 'true')
      await user.click(start)
      await user.click(start)
      expect(onStart).not.toHaveBeenCalled()
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
      await user.keyboard('{Escape}')
      expect(onOpenChange).not.toHaveBeenCalled()
    })
  })

  it('is 480 px wide, and stacks its buttons with the primary on top on a phone', () => {
    setup()
    expect(screen.getByRole('alertdialog')).toHaveClass('max-w-120')
    const actions = screen.getByRole('button', { name: 'Cancel' }).parentElement
    expect(actions).toHaveClass('max-sm:flex-col-reverse')
  })

  it('renders nothing when closed', () => {
    render(<TourStartDialog open={false} onOpenChange={() => {}} onStart={() => {}} />)
    expect(screen.queryByRole('alertdialog')).toBeNull()
  })
})
