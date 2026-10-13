import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { EmptyState } from './empty-state'

describe('EmptyState', () => {
  it('says what is missing, as a status', () => {
    render(<EmptyState message="No one matches these filters." />)
    expect(screen.getByRole('status')).toHaveTextContent('No one matches these filters.')
  })

  it('offers one action, which runs when pressed', async () => {
    const onAction = vi.fn<() => void>()
    render(
      <EmptyState
        message="No one matches these filters."
        action={{ label: 'Clear filters', onAction }}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(onAction).toHaveBeenCalledTimes(1)
  })

  it('has no button without an action', () => {
    render(<EmptyState message="Nothing here." />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('offers a second action beside the first, which runs when pressed', async () => {
    const onSecond = vi.fn<() => void>()
    render(
      <EmptyState
        message="Nothing."
        action={{ label: 'Clear', onAction: vi.fn<() => void>() }}
        secondaryAction={{ label: 'Ask', onAction: onSecond }}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(onSecond).toHaveBeenCalledTimes(1)
  })
})
