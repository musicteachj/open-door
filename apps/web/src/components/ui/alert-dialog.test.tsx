import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import {
  AlertDialog,
  AlertDialogActions,
  AlertDialogCancel,
  AlertDialogConfirm,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
  AlertDialogTrigger,
} from './alert-dialog'

type ExampleProps = {
  busy?: boolean
  onConfirm?: () => void
  onOpenAutoFocus?: (event: Event) => void
}

function Example({ busy = false, onConfirm, onOpenAutoFocus }: ExampleProps) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button>Elsewhere</button>
      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogTrigger asChild>
          <button>Cancel PTO</button>
        </AlertDialogTrigger>
        <AlertDialogContent busy={busy} onOpenAutoFocus={onOpenAutoFocus}>
          <AlertDialogTitle>Cancel your time off on Wednesday, December 23?</AlertDialogTitle>
          <AlertDialogDescription>8 hours go back to your balance.</AlertDialogDescription>
          <AlertDialogActions>
            <AlertDialogCancel>Keep it</AlertDialogCancel>
            <AlertDialogConfirm onClick={onConfirm}>Cancel request</AlertDialogConfirm>
          </AlertDialogActions>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

async function open() {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Cancel PTO' }))
  return user
}

describe('AlertDialog', () => {
  it('is an alertdialog named by its title and described by its body', async () => {
    render(<Example />)
    await open()
    const dialog = screen.getByRole('alertdialog', {
      name: 'Cancel your time off on Wednesday, December 23?',
    })
    expect(dialog).toHaveAccessibleDescription('8 hours go back to your balance.')
  })

  it('puts focus on the cancel button, the safe choice', async () => {
    render(<Example />)
    await open()
    expect(screen.getByRole('button', { name: 'Keep it' })).toHaveFocus()
  })

  it('lets the caller choose where focus starts', async () => {
    render(
      <Example
        onOpenAutoFocus={(event) => {
          event.preventDefault()
          screen.getByRole('button', { name: 'Cancel request' }).focus()
        }}
      />,
    )
    await open()
    expect(screen.getByRole('button', { name: 'Cancel request' })).toHaveFocus()
  })

  it('keeps Tab inside, wrapping in both directions', async () => {
    render(<Example />)
    const user = await open()
    await user.tab()
    expect(screen.getByRole('button', { name: 'Cancel request' })).toHaveFocus()
    await user.tab()
    expect(screen.getByRole('button', { name: 'Keep it' })).toHaveFocus()
    await user.tab({ shift: true })
    expect(screen.getByRole('button', { name: 'Cancel request' })).toHaveFocus()
  })

  it('hides the page behind it', async () => {
    render(<Example />)
    await open()
    expect(screen.queryByRole('button', { name: 'Elsewhere' })).not.toBeInTheDocument()
  })

  it('closes on Escape and returns focus to the trigger', async () => {
    render(<Example />)
    const user = await open()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel PTO' })).toHaveFocus()
  })

  it('closes from the cancel button and returns focus to the trigger', async () => {
    render(<Example />)
    const user = await open()
    await user.click(screen.getByRole('button', { name: 'Keep it' }))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel PTO' })).toHaveFocus()
  })

  it('ignores Escape while busy', async () => {
    render(<Example busy />)
    const user = await open()
    await user.keyboard('{Escape}')
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
  })

  it('does not close on a press outside it', async () => {
    render(<Example />)
    const user = await open()
    const overlay = document.querySelector('[data-slot="alert-dialog-overlay"]')!
    await user.pointer({ keys: '[MouseLeft]', target: overlay })
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
  })

  it('leaves the dialog open when the confirm button is pressed, for the caller to close', async () => {
    const onConfirm = vi.fn<() => void>()
    render(<Example onConfirm={onConfirm} />)
    const user = await open()
    await user.click(screen.getByRole('button', { name: 'Cancel request' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
  })

  it('fills the window with the scrim, so it covers the sidebar too', async () => {
    render(<Example />)
    await open()
    const overlay = document.querySelector('[data-slot="alert-dialog-overlay"]')!
    expect(overlay).toHaveClass('fixed', 'inset-0', 'bg-scrim')
  })

  it('lets the dialog shrink to the window, with the overlay padding as its margins', async () => {
    render(<Example />)
    await open()
    // A flex overlay gives the dialog a definite width to fill; a grid sized to its content let the
    // dialog run past the right edge on a phone. Layout itself is checked in the browser at 390 px.
    const overlay = document.querySelector('[data-slot="alert-dialog-overlay"]')!
    expect(overlay).toHaveClass('flex', 'justify-center', 'p-6', 'max-sm:p-4')
    expect(overlay).not.toHaveClass('grid')
  })

  it('is 480 px wide and padded 24 px on a raised surface', async () => {
    render(<Example />)
    await open()
    expect(screen.getByRole('alertdialog')).toHaveClass(
      'w-full',
      'max-w-120',
      'p-6',
      'bg-surface-raised',
      'rounded-xl',
      'shadow-md',
    )
  })

  it('right-aligns its actions, and stacks them with the confirm on top on a phone', async () => {
    render(<Example />)
    await open()
    const actions = screen.getByRole('button', { name: 'Keep it' }).parentElement!
    expect(actions).toHaveClass('justify-end', 'gap-3', 'max-sm:flex-col-reverse')
    expect(screen.getByRole('button', { name: 'Keep it' })).toHaveClass('max-sm:w-full')
    expect(screen.getByRole('button', { name: 'Cancel request' })).toHaveClass('max-sm:w-full')
  })

  it('disables the cancel button while busy, as well as Escape', async () => {
    render(<Example busy />)
    await open()
    expect(screen.getByRole('button', { name: 'Keep it' })).toBeDisabled()
  })

  it('shows the confirm button busy and does not run it again', async () => {
    const onConfirm = vi.fn<() => void>()
    render(
      <AlertDialog open>
        <AlertDialogContent busy>
          <AlertDialogTitle>Approve?</AlertDialogTitle>
          <AlertDialogDescription>Body</AlertDialogDescription>
          <AlertDialogActions>
            <AlertDialogCancel disabled>Go back</AlertDialogCancel>
            <AlertDialogConfirm loading onClick={onConfirm}>
              Approving…
            </AlertDialogConfirm>
          </AlertDialogActions>
        </AlertDialogContent>
      </AlertDialog>,
    )
    const confirm = screen.getByRole('button', { name: 'Approving…' })
    expect(confirm).toHaveAttribute('aria-busy', 'true')
    await userEvent.setup().click(confirm)
    expect(onConfirm).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Go back' })).toBeDisabled()
  })
})
