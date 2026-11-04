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

  it('keeps a secondary action and a ghost second action by default', () => {
    render(
      <EmptyState
        message="Nothing."
        action={{ label: 'Clear', onAction: vi.fn<() => void>() }}
        secondaryAction={{ label: 'Ask', onAction: vi.fn<() => void>() }}
      />,
    )
    expect(screen.getByRole('button', { name: 'Clear' })).toHaveClass('bg-surface-raised')
    expect(screen.getByRole('button', { name: 'Ask' })).toHaveClass('bg-transparent')
  })

  it('can make the action primary and the second action secondary', () => {
    render(
      <EmptyState
        message="Nothing."
        action={{ label: 'Ask a question', onAction: vi.fn<() => void>(), variant: 'primary' }}
        secondaryAction={{
          label: 'Take the tour',
          onAction: vi.fn<() => void>(),
          variant: 'secondary',
        }}
      />,
    )
    expect(screen.getByRole('button', { name: 'Ask a question' })).toHaveClass('bg-primary')
    expect(screen.getByRole('button', { name: 'Take the tour' })).toHaveClass('bg-surface-raised')
  })
})
