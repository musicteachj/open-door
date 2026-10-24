import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { ZARA } from '@/app/gallery/fixtures/timeoff'
import { DecisionDialog } from './decision-dialog'

const FACTS = 'Monday, November 9 to Tuesday, November 10, 16 hours (2 days).'

type Props = Partial<React.ComponentProps<typeof DecisionDialog>>

function Dialog(props: Props) {
  const [note, setNote] = useState(props.note ?? '')
  return (
    <DecisionDialog
      open
      onOpenChange={() => {}}
      kind="approve"
      person={ZARA}
      facts={FACTS}
      note={note}
      onNoteChange={setNote}
      onConfirm={() => {}}
      {...props}
    />
  )
}

describe('DecisionDialog, approve', () => {
  it('is an alert dialog titled for the request, described by the facts and where it shows', () => {
    render(<Dialog />)
    const dialog = screen.getByRole('alertdialog', { name: 'Approve Zara Bautista’s PTO?' })
    expect(dialog).toHaveAccessibleDescription(`${FACTS} Zara will see it on the Time off page.`)
  })

  it('starts focus on Go back and has Go back, then Approve', () => {
    render(<Dialog />)
    expect(screen.getByRole('button', { name: 'Go back' })).toHaveFocus()
    const buttons = within(screen.getByRole('alertdialog')).getAllByRole('button')
    expect(buttons.map((button) => button.textContent)).toEqual(['Go back', 'Approve'])
  })

  it('has no note field', () => {
    render(<Dialog />)
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('confirms with the standard primary button, never destructive', () => {
    render(<Dialog />)
    const confirm = screen.getByRole('button', { name: 'Approve' })
    expect(confirm).toHaveClass('bg-primary')
    expect(confirm).not.toHaveClass('bg-danger')
  })

  it('calls onConfirm, and asks to close for Go back and for Escape', async () => {
    const onConfirm = vi.fn<() => void>()
    const onOpenChange = vi.fn<(open: boolean) => void>()
    const user = userEvent.setup()
    render(<Dialog onConfirm={onConfirm} onOpenChange={onOpenChange} />)
    await user.click(screen.getByRole('button', { name: 'Approve' }))
    expect(onConfirm).toHaveBeenCalledOnce()
    await user.click(screen.getByRole('button', { name: 'Go back' }))
    await user.keyboard('{Escape}')
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onOpenChange).toHaveBeenCalledTimes(2)
  })
})

describe('DecisionDialog, deny', () => {
  it('is titled Deny, starts focus in the note, and describes only the facts', () => {
    render(<Dialog kind="deny" />)
    const dialog = screen.getByRole('alertdialog', { name: 'Deny Zara Bautista’s PTO?' })
    expect(dialog).toHaveAccessibleDescription(FACTS)
    expect(screen.getByRole('textbox', { name: 'Note to Zara (optional)' })).toHaveFocus()
  })

  it('has Go back, then Deny as a standard primary button', () => {
    render(<Dialog kind="deny" />)
    const buttons = within(screen.getByRole('alertdialog')).getAllByRole('button')
    expect(buttons.map((button) => button.textContent)).toEqual(['Go back', 'Deny'])
    expect(buttons[1]).toHaveClass('bg-primary')
  })

  it('shows the typed note and its count', () => {
    render(<Dialog kind="deny" note="Inventory runs that week." />)
    expect(screen.getByRole('textbox')).toHaveValue('Inventory runs that week.')
    expect(screen.getByText('25 of 300')).toBeInTheDocument()
  })
})

describe('DecisionDialog, deciding', () => {
  it('shows Approving… busy and locks Go back', () => {
    render(<Dialog deciding />)
    const confirm = screen.getByRole('button', { name: 'Approving…' })
    expect(confirm).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('button', { name: 'Go back' })).toBeDisabled()
  })

  it('shows Denying… and locks the note too', () => {
    render(<Dialog kind="deny" deciding />)
    expect(screen.getByRole('button', { name: 'Denying…' })).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('textbox')).toBeDisabled()
  })

  it('ignores Escape while deciding', async () => {
    const onOpenChange = vi.fn<(open: boolean) => void>()
    const user = userEvent.setup()
    render(<Dialog deciding onOpenChange={onOpenChange} />)
    await user.keyboard('{Escape}')
    expect(onOpenChange).not.toHaveBeenCalled()
  })

  it('does not confirm again on another press', async () => {
    const onConfirm = vi.fn<() => void>()
    const user = userEvent.setup()
    render(<Dialog deciding onConfirm={onConfirm} />)
    await user.click(screen.getByRole('button', { name: 'Approving…' }))
    expect(onConfirm).not.toHaveBeenCalled()
  })
})

describe('DecisionDialog, focus on close', () => {
  it('lets the page choose where focus goes when the dialog closes', async () => {
    const onCloseAutoFocus = vi.fn<(event: Event) => void>((event) => event.preventDefault())
    function Page() {
      const [open, setOpen] = useState(true)
      return (
        <DecisionDialog
          open={open}
          onOpenChange={setOpen}
          kind="approve"
          person={ZARA}
          facts={FACTS}
          note=""
          onNoteChange={() => {}}
          onConfirm={() => {}}
          onCloseAutoFocus={onCloseAutoFocus}
        />
      )
    }
    const user = userEvent.setup()
    render(<Page />)
    await user.click(screen.getByRole('button', { name: 'Go back' }))
    expect(onCloseAutoFocus).toHaveBeenCalledOnce()
  })
})

describe('DecisionDialog, closed', () => {
  it('renders nothing', () => {
    render(<Dialog open={false} />)
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })
})
