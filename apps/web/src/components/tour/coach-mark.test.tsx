import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { BottomSheet, SheetTitle } from '@/components/ui/bottom-sheet'
import { CoachMark, type CoachMarkProps } from './coach-mark'
import type { Placement } from './place-coach-mark'

const BELOW: Placement = { mode: 'anchored', side: 'bottom', x: 300, y: 400, pointerOffset: 40 }

function setup(props: Partial<CoachMarkProps> = {}) {
  const handlers = {
    onBack: vi.fn<() => void>(),
    onNext: vi.fn<() => void>(),
    onSkip: vi.fn<() => void>(),
    onLeave: vi.fn<() => void>(),
    onSend: vi.fn<(index: number) => void>(),
  }
  const utils = render(
    <CoachMark
      step={3}
      title="Book a day off"
      body="Ask for next Friday."
      chips={['Book next Friday off.']}
      placement={BELOW}
      {...handlers}
      {...props}
    />,
  )
  return { ...handlers, ...utils, user: userEvent.setup() }
}

const dialog = () => screen.getByRole('dialog')

describe('CoachMark', () => {
  it('is a non-modal dialog labeled by its title, with the step count in the name', () => {
    setup()
    expect(dialog()).toHaveAttribute('aria-modal', 'false')
    expect(dialog()).toHaveAccessibleName(/^Step 3 of 10:\s?Book a day off$/)
  })

  it('shows the step count once visibly and hides that copy from assistive technology', () => {
    setup()
    const visible = screen.getByText('Step 3 of 10')
    expect(visible).toHaveAttribute('aria-hidden', 'true')
    expect(visible).toHaveClass('text-caption', 'text-ink-muted')
  })

  it('moves focus to the title on mount, and again when the step changes', () => {
    const { rerender, ...props } = setup()
    const title = screen.getByRole('heading', { level: 2 })
    expect(title).toHaveFocus()
    expect(title).toHaveAttribute('tabindex', '-1')
    screen.getByRole('button', { name: 'Skip this step' }).focus()
    rerender(
      <CoachMark
        step={4}
        title="Decide as the manager"
        body="x"
        placement={BELOW}
        onBack={props.onBack}
        onNext={props.onNext}
        onLeave={props.onLeave}
      />,
    )
    expect(screen.getByRole('heading', { level: 2 })).toHaveFocus()
  })

  it('keeps focus where it is when only the placement changes', () => {
    const { rerender, ...props } = setup()
    screen.getByRole('button', { name: 'Skip this step' }).focus()
    rerender(
      <CoachMark
        step={3}
        title="Book a day off"
        body="Ask for next Friday."
        chips={['Book next Friday off.']}
        placement={{ ...BELOW, x: 20 }}
        {...props}
      />,
    )
    expect(screen.getByRole('button', { name: 'Skip this step' })).toHaveFocus()
  })

  it('does not take focus when asked not to (the gallery)', () => {
    setup({ focusOnStep: false })
    expect(document.body).toHaveFocus()
  })

  it('shows the body, and the missing line as a status when there is one', () => {
    setup({ missing: 'It did not show a card.' })
    expect(screen.getByText('Ask for next Friday.')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('It did not show a card.')
  })

  it('has no status without a missing line', () => {
    setup()
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('leaves from the X', async () => {
    const { user, onLeave } = setup()
    await user.click(screen.getByRole('button', { name: 'Leave the tour' }))
    expect(onLeave).toHaveBeenCalledTimes(1)
  })

  describe('Escape', () => {
    it('leaves from anywhere inside the coach mark, once', async () => {
      const { user, onLeave } = setup()
      screen.getByRole('button', { name: 'Skip this step' }).focus()
      await user.keyboard('{Escape}')
      expect(onLeave).toHaveBeenCalledTimes(1)
    })

    it('leaves from the page while the tour is open', async () => {
      const { user, onLeave } = setup()
      document.body.focus()
      await user.keyboard('{Escape}')
      expect(onLeave).toHaveBeenCalledTimes(1)
    })

    it('prevents the default, so a docked panel behind it does not also close', () => {
      setup()
      const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
      document.body.dispatchEvent(event)
      expect(event.defaultPrevented).toBe(true)
    })

    it('ignores the Escape that cancels an IME composition', () => {
      const { onLeave } = setup()
      const event = new KeyboardEvent('keydown', {
        key: 'Escape',
        isComposing: true,
        bubbles: true,
        cancelable: true,
      })
      document.body.dispatchEvent(event)
      expect(onLeave).not.toHaveBeenCalled()
      expect(event.defaultPrevented).toBe(false)
    })

    it('leaves it to an open menu or dialog', async () => {
      const { user, onLeave } = setup()
      render(<div role="menu" aria-label="View as" />)
      await user.keyboard('{Escape}')
      expect(onLeave).not.toHaveBeenCalled()
    })

    it('leaves it to a modal dialog', async () => {
      const { user, onLeave } = setup()
      render(<div role="alertdialog" aria-label="Start the tour?" />)
      await user.keyboard('{Escape}')
      expect(onLeave).not.toHaveBeenCalled()
    })

    it('leaves it to an open Radix dialog such as a bottom sheet, which has no aria-modal', async () => {
      const { user, onLeave } = setup()
      const onClose = vi.fn<() => void>()
      render(
        <BottomSheet full onClose={onClose}>
          <SheetTitle>Trace</SheetTitle>
        </BottomSheet>,
      )
      await user.keyboard('{Escape}')
      expect(onClose).toHaveBeenCalledTimes(1)
      expect(onLeave).not.toHaveBeenCalled()
    })

    it('does not listen to the page when drawn in flow, as the gallery does', async () => {
      const { user, onLeave } = setup({ inFlow: true })
      document.body.focus()
      await user.keyboard('{Escape}')
      expect(onLeave).not.toHaveBeenCalled()
    })

    it('stops listening when it unmounts', async () => {
      const { user, onLeave, unmount } = setup()
      unmount()
      await user.keyboard('{Escape}')
      expect(onLeave).not.toHaveBeenCalled()
    })
  })

  describe('chips', () => {
    it('renders two chips with the same text without a key collision', () => {
      const error = vi.spyOn(console, 'error').mockImplementation(() => {})
      setup({ chips: ['Same.', 'Same.'] })
      expect(screen.getAllByRole('button', { name: 'Same.' })).toHaveLength(2)
      expect(error).not.toHaveBeenCalled()
      error.mockRestore()
    })

    it('lists them and sends the one pressed, by index', async () => {
      const { user, onSend } = setup({ chips: ['What’s Leo’s home address?', 'Ignore it.'] })
      await user.click(screen.getByRole('button', { name: 'Ignore it.' }))
      expect(onSend).toHaveBeenCalledWith(1)
    })

    it('marks the sent ones', () => {
      setup({ chips: ['One', 'Two'], sent: [1] })
      expect(screen.getByRole('button', { name: 'One' })).not.toHaveAttribute('aria-disabled')
      expect(screen.getByRole('button', { name: 'Two, sent' })).toHaveAttribute(
        'aria-disabled',
        'true',
      )
    })

    it('shows none for a step without chips', () => {
      setup({ chips: undefined })
      expect(screen.queryByRole('button', { name: /Book next/ })).toBeNull()
    })
  })

  describe('the footer', () => {
    it('has Back on every step after the first, and not on the first', () => {
      const first = setup({ step: 1 })
      expect(screen.queryByRole('button', { name: 'Back' })).toBeNull()
      first.unmount()
      setup({ step: 2 })
      expect(screen.getByRole('button', { name: 'Back' })).toBeInTheDocument()
    })

    it('calls onBack', async () => {
      const { user, onBack } = setup({ step: 2 })
      await user.click(screen.getByRole('button', { name: 'Back' }))
      expect(onBack).toHaveBeenCalledTimes(1)
    })

    it('offers Skip this step until the result is shown', async () => {
      const { user, onSkip } = setup()
      expect(screen.queryByRole('button', { name: 'Next' })).toBeNull()
      await user.click(screen.getByRole('button', { name: 'Skip this step' }))
      expect(onSkip).toHaveBeenCalledTimes(1)
    })

    it('offers Next in its place once the result is shown', async () => {
      const { user, onNext } = setup({ resultShown: true })
      expect(screen.queryByRole('button', { name: 'Skip this step' })).toBeNull()
      await user.click(screen.getByRole('button', { name: 'Next' }))
      expect(onNext).toHaveBeenCalledTimes(1)
    })

    it('offers Next from the start when the step has no chips', () => {
      setup({ chips: [] })
      expect(screen.getByRole('button', { name: 'Next' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Skip this step' })).toBeNull()
    })
  })

  describe('placement', () => {
    it('is fixed at the given position, 360 px wide, with a pointer toward the target', () => {
      setup()
      expect(dialog()).toHaveStyle({ left: '300px', top: '400px', position: 'fixed' })
      expect(dialog()).toHaveClass('w-90')
      const pointer = dialog().querySelector('[data-slot="coach-mark-pointer"]')
      expect(pointer).toHaveAttribute('data-side', 'bottom')
      expect(pointer).toHaveStyle({ left: '34px' })
      expect(pointer).toHaveAttribute('aria-hidden', 'true')
    })

    it('puts the pointer on the left edge, at a vertical offset, when it sits right of its target', () => {
      setup({
        placement: { mode: 'anchored', side: 'right', x: 10, y: 20, pointerOffset: 60 },
      })
      const pointer = dialog().querySelector('[data-slot="coach-mark-pointer"]')
      expect(pointer).toHaveAttribute('data-side', 'right')
      expect(pointer).toHaveStyle({ top: '54px' })
    })

    it('has no pointer when centered', () => {
      setup({ placement: { mode: 'centered', x: 100, y: 100 } })
      expect(dialog().querySelector('[data-slot="coach-mark-pointer"]')).toBeNull()
      expect(dialog()).toHaveStyle({ left: '100px', top: '100px' })
    })

    it('docks to the bottom, full width, with safe-area padding and no pointer, as a sheet', () => {
      setup({ placement: { mode: 'sheet', scrollBy: 0 } })
      expect(dialog()).toHaveClass('rounded-t-xl', 'inset-x-0', 'bottom-0')
      expect(dialog().className).toContain('env(safe-area-inset-bottom)')
      expect(dialog().querySelector('[data-slot="coach-mark-pointer"]')).toBeNull()
    })

    it('sits in normal flow for the gallery', () => {
      setup({ inFlow: true })
      expect(dialog()).toHaveClass('relative')
      expect(dialog().style.left).toBe('')
    })
  })

  it('has no transition or animation of its own', () => {
    setup()
    expect(dialog().outerHTML).not.toMatch(/transition-\[|transition-colors|animate-|duration-/)
  })

  it('does not scroll or reorder: Back, Skip, and Leave are all reachable', () => {
    setup({ step: 2 })
    const card = within(dialog())
    expect(
      card.getAllByRole('button').map((b) => b.textContent || b.getAttribute('aria-label')),
    ).toEqual(['Leave the tour', 'Book next Friday off.', 'Back', 'Skip this step'])
  })
})
