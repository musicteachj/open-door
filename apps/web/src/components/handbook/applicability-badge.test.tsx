import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ApplicabilityBadge } from './applicability-badge'

describe('ApplicabilityBadge', () => {
  it('reads "Applies to:" then the API label', () => {
    render(<ApplicabilityBadge label="Hourly staff in California" />)
    expect(screen.getByText('Applies to:')).toBeInTheDocument()
    expect(screen.getByText('Hourly staff in California')).toBeInTheDocument()
  })

  it('shows the label as given, even "Everyone"', () => {
    render(<ApplicabilityBadge label="Everyone" />)
    expect(screen.getByText('Everyone')).toBeInTheDocument()
  })

  it('shows only the bare value in the text variant', () => {
    render(<ApplicabilityBadge label="Denver HQ" variant="text" />)
    expect(screen.getByText('Denver HQ')).toBeInTheDocument()
    expect(screen.queryByText('Applies to:')).not.toBeInTheDocument()
  })
})
