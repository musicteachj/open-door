import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AppliesMarker } from './applies-marker'

describe('AppliesMarker', () => {
  it('says "Applies to you" with a check icon, hidden from screen readers', () => {
    const { container } = render(<AppliesMarker applies />)
    const text = screen.getByText('Applies to you')
    expect(text).toBeInTheDocument()
    const icon = container.querySelector('svg')
    expect(icon).toHaveClass('lucide-check')
    expect(icon).toHaveAttribute('aria-hidden', 'true')
  })

  it('says "Doesn\'t apply to you" with a minus icon, hidden from screen readers', () => {
    const { container } = render(<AppliesMarker applies={false} />)
    expect(screen.getByText("Doesn't apply to you")).toBeInTheDocument()
    const icon = container.querySelector('svg')
    expect(icon).toHaveClass('lucide-minus')
    expect(icon).toHaveAttribute('aria-hidden', 'true')
  })

  it('mutes the "no" variant and tints the "yes" icon with the primary color', () => {
    const { container, rerender } = render(<AppliesMarker applies />)
    expect(container.querySelector('svg')).toHaveClass('text-primary')
    rerender(<AppliesMarker applies={false} />)
    expect(screen.getByText("Doesn't apply to you").closest('span')).toHaveClass('text-ink-muted')
  })
})
