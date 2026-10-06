import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { TryAskingList } from './try-asking-list'

const items = ['How many sick days do I get?', 'Book next Friday off']

describe('TryAskingList', () => {
  it('is a labeled region holding a list with one button per question', () => {
    render(<TryAskingList items={items} onPick={() => {}} />)
    const region = screen.getByRole('region', { name: 'Try asking' })
    expect(within(region).getAllByRole('listitem')).toHaveLength(2)
    for (const question of items) {
      expect(within(region).getByRole('button', { name: question })).toBeInTheDocument()
    }
  })

  it('takes its label from a prop', () => {
    render(<TryAskingList label="Suggestions" items={items} onPick={() => {}} />)
    expect(screen.getByRole('region', { name: 'Suggestions' })).toBeInTheDocument()
  })

  it('calls onPick with the question, and nothing else', async () => {
    const onPick = vi.fn<(question: string) => void>()
    render(<TryAskingList items={items} onPick={onPick} />)
    await userEvent.click(screen.getByRole('button', { name: 'Book next Friday off' }))
    expect(onPick).toHaveBeenCalledExactlyOnceWith('Book next Friday off')
  })

  it('never submits a surrounding form', async () => {
    const onSubmit = vi.fn<() => void>()
    render(
      <form
        onSubmit={(event) => {
          event.preventDefault()
          onSubmit()
        }}
      >
        <TryAskingList items={items} onPick={() => {}} />
      </form>,
    )
    await userEvent.click(screen.getByRole('button', { name: items[0] }))
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('renders no list when there are no questions', () => {
    render(<TryAskingList items={[]} onPick={() => {}} />)
    expect(screen.queryByRole('region')).not.toBeInTheDocument()
  })
})
