import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { FeedbackSections } from './feedback-sections'

// The browser tests address each state by its heading's id, so the ids are part of the contract.
const IDS = [
  'banner-default',
  'banner-no-dismiss',
  'inline-error-retry',
  'inline-error-message',
  'full-page-message-session-expired',
  'full-page-message-not-found',
  'full-page-message-error',
]

describe('FeedbackSections', () => {
  it('has a heading with a stable id for every state', () => {
    const { container } = render(<FeedbackSections />)
    const missing = IDS.filter((id) => container.querySelector(`h3#${id}`) === null)
    expect(missing).toEqual([])
  })

  it('does not take focus, so the page keeps its own first Tab target', () => {
    render(<FeedbackSections />)
    expect(document.body).toHaveFocus()
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(3)
  })
})
