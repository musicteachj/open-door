import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { CaseStatusDialog, type CaseStatusDialogProps } from './case-status-dialog'

function setup(props: Partial<CaseStatusDialogProps> = {}) {
  const onOpenChange = vi.fn<(open: boolean) => void>()
  const onConfirm = vi.fn<() => void>()
  render(
    <CaseStatusDialog
      open
      kind="review"
      firstName="Priya"
      onOpenChange={onOpenChange}
      onConfirm={onConfirm}
      {...props}
    />,
  )
  return { onOpenChange, onConfirm }
}

describe('CaseStatusDialog', () => {
  it('start review: an alert dialog named by its title and described by the body', () => {
    setup()
    const dialog = screen.getByRole('alertdialog', { name: 'Start review of this case?' })
    expect(dialog).toHaveAccessibleDescription('Priya will see “HR is reviewing” in My cases.')
  })

  it('close: the title and body, with the period inside the quotation marks', () => {
    setup({ kind: 'close' })
    const dialog = screen.getByRole('alertdialog', { name: 'Close this case?' })
    expect(dialog).toHaveAccessibleDescription(
      'Priya will see “HR has finished its review.” A closed case can’t be reopened in Open Door.',
    )
  })

  it.each([
    ['review', 'Start review'],
    ['close', 'Close case'],
  ] as const)('%s: Cancel gets focus first, then the standard primary %s', (kind, label) => {
    setup({ kind })
    const dialog = screen.getByRole('alertdialog')
    const buttons = within(dialog).getAllByRole('button')
    expect(buttons.map((b) => b.textContent)).toEqual(['Cancel', label])
    expect(buttons[0]).toHaveFocus()
    // Standard primary, never the destructive red, even when closing.
    expect(buttons[1]).toHaveClass('bg-primary')
    expect(buttons[1]!.className).not.toMatch(/danger/)
  })

  it('traps focus between Cancel and the primary', async () => {
    setup()
    const dialog = screen.getByRole('alertdialog')
    const [cancel, confirm] = within(dialog).getAllByRole('button')
    await userEvent.tab()
    expect(confirm).toHaveFocus()
    await userEvent.tab()
    expect(cancel).toHaveFocus()
  })

  it('Cancel and Escape close it', async () => {
    const { onOpenChange } = setup()
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onOpenChange).toHaveBeenLastCalledWith(false)
    await userEvent.keyboard('{Escape}')
    expect(onOpenChange).toHaveBeenCalledTimes(2)
  })

  it('Confirm calls onConfirm and leaves it to the page to close', async () => {
    const { onConfirm, onOpenChange } = setup({ kind: 'close' })
    await userEvent.click(screen.getByRole('button', { name: 'Close case' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(onOpenChange).not.toHaveBeenCalled()
  })

  it('while pending, the primary is busy and does nothing, Cancel is off, and Escape is ignored', async () => {
    const { onConfirm, onOpenChange } = setup({ pending: true })
    const confirm = screen.getByRole('button', { name: 'Starting…' })
    expect(confirm).toHaveAttribute('aria-busy', 'true')
    await userEvent.click(confirm)
    expect(onConfirm).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    await userEvent.keyboard('{Escape}')
    expect(onOpenChange).not.toHaveBeenCalled()
  })

  it('hands the page the close-focus event, to return focus to what opened it', async () => {
    const onCloseAutoFocus = vi.fn<(event: Event) => void>((event) => event.preventDefault())
    const { rerender } = render(
      <CaseStatusDialog
        open
        kind="review"
        firstName="Priya"
        onOpenChange={() => {}}
        onConfirm={() => {}}
        onCloseAutoFocus={onCloseAutoFocus}
      />,
    )
    rerender(
      <CaseStatusDialog
        open={false}
        kind="review"
        firstName="Priya"
        onOpenChange={() => {}}
        onConfirm={() => {}}
        onCloseAutoFocus={onCloseAutoFocus}
      />,
    )
    await waitFor(() => expect(onCloseAutoFocus).toHaveBeenCalledTimes(1))
  })
})
