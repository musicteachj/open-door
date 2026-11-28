import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Skeleton } from './skeleton'

describe('Skeleton', () => {
  it('is hidden from assistive technology, like the design’s skeleton row', () => {
    render(<Skeleton data-testid="skeleton" />)
    expect(screen.getByTestId('skeleton')).toHaveAttribute('aria-hidden', 'true')
    expect(screen.queryByRole('presentation')).not.toBeInTheDocument()
  })

  it('is a quiet 12 px bar with 6 px corners and a soft pulse only where motion is allowed', () => {
    render(<Skeleton data-testid="skeleton" />)
    const skeleton = screen.getByTestId('skeleton')
    expect(skeleton).toHaveClass('h-3', 'rounded-xs', 'bg-surface-hover', 'block')
    expect(skeleton).toHaveClass('motion-safe:animate-pulse-soft')
    // The pulse is the only animation, and only behind motion-safe.
    expect(skeleton.className.match(/\S*animate-\S*/g)).toEqual(['motion-safe:animate-pulse-soft'])
  })

  it('takes a size and shape from the caller', () => {
    render(<Skeleton data-testid="skeleton" className="size-8 rounded-full" />)
    const skeleton = screen.getByTestId('skeleton')
    expect(skeleton).toHaveClass('size-8', 'rounded-full')
    expect(skeleton).not.toHaveClass('h-3', 'rounded-xs')
  })
})
