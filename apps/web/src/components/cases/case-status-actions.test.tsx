import { createRef } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { CaseStatusActions, type CaseStatusActionsProps } from './case-status-actions'

function setup(props: Partial<CaseStatusActionsProps> = {}) {
  const onStartReview = vi.fn<() => void>()
  const onClose = vi.fn<() => void>()
  render(
    <CaseStatusActions
      status="new"
      firstName="Priya"
      locked={false}
      onStartReview={onStartReview}
      onClose={onClose}
      {...props}
    />,
  )
  return { onStartReview, onClose }
}

describe('CaseStatusActions', () => {
  it('a new case offers Start review (primary) then Close case (secondary), in a named group', async () => {
    const { onStartReview, onClose } = setup()
    const group = screen.getByRole('group', { name: 'Change the status' })
    expect(group).toBeInTheDocument()
    const start = screen.getByRole('button', { name: 'Start review' })
    const close = screen.getByRole('button', { name: 'Close case' })
    expect(start).toHaveClass('bg-primary')
    expect(close).toHaveClass('bg-surface-raised')
    expect(start.compareDocumentPosition(close) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    await userEvent.click(start)
    await userEvent.click(close)
    expect(onStartReview).toHaveBeenCalledTimes(1)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('a case in review offers only Close case, secondary', () => {
    setup({ status: 'in_review' })
    expect(screen.queryByRole('button', { name: 'Start review' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Close case' })).toHaveClass('bg-surface-raised')
  })

  it('a closed case has no buttons and says it is closed', () => {
    setup({ status: 'closed' })
    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.getByText('This case is closed.')).toBeInTheDocument()
  })

  it('while locked, both buttons are aria-disabled, focusable, and described by the read-first line', async () => {
    const { onStartReview, onClose } = setup({ locked: true })
    const line = screen.getByText('Read Priya’s words before changing the status.')
    for (const name of ['Start review', 'Close case']) {
      const button = screen.getByRole('button', { name })
      expect(button).toHaveAttribute('aria-disabled', 'true')
      expect(button).not.toBeDisabled()
      expect(button).toHaveAccessibleDescription(line.textContent!)
      button.focus()
      expect(button).toHaveFocus()
      await userEvent.click(button)
    }
    expect(onStartReview).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('while locked, pressing Enter or Space does nothing either', async () => {
    const { onClose } = setup({ locked: true, status: 'in_review' })
    screen.getByRole('button', { name: 'Close case' }).focus()
    await userEvent.keyboard('{Enter} ')
    expect(onClose).not.toHaveBeenCalled()
  })

  it('unlocked, the buttons are not disabled and carry no description', () => {
    setup()
    const button = screen.getByRole('button', { name: 'Start review' })
    expect(button).not.toHaveAttribute('aria-disabled')
    expect(button).not.toHaveAttribute('aria-describedby')
    expect(screen.queryByText(/Read Priya/)).toBeNull()
  })

  it('hands the buttons to the page as refs, so focus can move after a confirm', () => {
    const startButtonRef = createRef<HTMLButtonElement>()
    const closeButtonRef = createRef<HTMLButtonElement>()
    setup({ startButtonRef, closeButtonRef })
    expect(startButtonRef.current).toBe(screen.getByRole('button', { name: 'Start review' }))
    expect(closeButtonRef.current).toBe(screen.getByRole('button', { name: 'Close case' }))
  })

  it('goes full width on a phone', () => {
    setup()
    expect(screen.getByRole('button', { name: 'Start review' })).toHaveClass('max-sm:w-full')
    expect(screen.getByRole('group').className).toContain('max-sm:flex-col')
  })
})
