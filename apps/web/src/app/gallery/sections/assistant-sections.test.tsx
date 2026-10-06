import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { AssistantSections } from './assistant-sections'

// The browser tests address each state by its heading's id, so the ids are part of the contract.
const IDS = [
  'composer-empty',
  'composer-typed',
  'composer-error',
  'composer-busy',
  'try-asking-default',
]

describe('AssistantSections', () => {
  it('has a heading with a stable id for every state', () => {
    const { container } = render(<AssistantSections />)
    const missing = IDS.filter((id) => container.querySelector(`h3#${id}`) === null)
    expect(missing).toEqual([])
  })

  it('shows the error state', () => {
    render(<AssistantSections />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('fills a composer from a "Try asking" row, without sending', async () => {
    render(<AssistantSections />)
    await userEvent.click(screen.getByRole('button', { name: 'Book next Friday off' }))
    const values = screen.getAllByRole('textbox').map((box) => (box as HTMLTextAreaElement).value)
    expect(values).toContain('Book next Friday off')
  })
})
