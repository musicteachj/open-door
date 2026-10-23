import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ZARA_WAITING } from '@/app/gallery/fixtures/timeoff'
import { CoverageLine } from './coverage-line'

describe('CoverageLine', () => {
  it('has the label with the people icon and a plain line for a colleague', () => {
    const { container } = render(<CoverageLine coverage={ZARA_WAITING.coverage!} multiDay />)
    expect(screen.getByText('Team coverage')).toBeInTheDocument()
    expect(
      screen.getByText('Also off: Vikram Morales, Tuesday, November 10 · PTO'),
    ).toBeInTheDocument()
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
    expect(container.querySelector('svg')).toHaveClass('text-ink-muted')
  })

  it('says no one else is off when there is no coverage', () => {
    render(<CoverageLine coverage={[]} multiDay={false} />)
    expect(screen.getByText('No one else on your team is off that day.')).toBeInTheDocument()
  })

  it('is plain ink: no color class and no alert role on the text', () => {
    const { container } = render(<CoverageLine coverage={ZARA_WAITING.coverage!} multiDay />)
    const line = screen.getByText(/Also off/)
    expect(line).toHaveClass('text-ink')
    expect(container.innerHTML).not.toMatch(/danger|warning|marker|success|role="alert"/)
  })
})
