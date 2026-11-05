import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { EmptyCell } from './empty-cell'

describe('EmptyCell', () => {
  it('shows a dash to the eye and "None" to a screen reader', () => {
    render(<EmptyCell />)
    expect(screen.getByText('–')).toHaveAttribute('aria-hidden', 'true')
    expect(screen.getByText('None')).toHaveClass('sr-only')
  })

  it('says what is hidden when told', () => {
    render(<EmptyCell hidden="Not in the set" />)
    expect(screen.getByText('Not in the set')).toHaveClass('sr-only')
  })
})
