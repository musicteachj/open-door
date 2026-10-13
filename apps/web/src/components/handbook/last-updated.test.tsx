import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { LastUpdated } from './last-updated'

describe('LastUpdated', () => {
  it('writes "Last updated Sep 12, 2026" from the API date', () => {
    render(<LastUpdated date="2026-09-12" />)
    expect(screen.getByText('Last updated Sep 12, 2026')).toBeInTheDocument()
  })

  it('renders only the date when bare', () => {
    render(<LastUpdated date="2026-09-12" bare />)
    expect(screen.getByText('Sep 12, 2026')).toBeInTheDocument()
  })

  it('uses tabular figures', () => {
    render(<LastUpdated date="2026-09-12" />)
    expect(screen.getByText('Last updated Sep 12, 2026')).toHaveClass('tabular-nums')
  })
})
