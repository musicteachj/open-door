import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SkeletonRow } from './skeleton-row'

describe('SkeletonRow', () => {
  it('is hidden from screen readers and holds nothing to read', () => {
    const { container } = render(<SkeletonRow />)
    const row = container.firstElementChild!
    expect(row).toHaveAttribute('aria-hidden', 'true')
    expect(row).toHaveTextContent('')
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it("has no shimmer, only the skeleton's soft pulse behind motion-safe (ADR 0025)", () => {
    const { container } = render(<SkeletonRow variant={2} />)
    expect(container.innerHTML).not.toMatch(/shimmer/)
    const animations = container.innerHTML.match(/[\w:-]*animate-[\w-]+/g) ?? []
    expect(animations.length).toBeGreaterThan(0)
    expect(new Set(animations)).toEqual(new Set(['motion-safe:animate-pulse-soft']))
  })

  it('varies its bar widths by variant, in the four steps the sketch has', () => {
    const widths = (variant: number) => {
      const { container, unmount } = render(<SkeletonRow variant={variant} />)
      const result = Array.from(container.querySelectorAll<HTMLElement>('[data-slot="skeleton"]'))
        .map((bar) => bar.style.width)
        .filter(Boolean)
      unmount()
      return result
    }
    expect(widths(0)).toEqual(['46%', '62%', '50%', '58%'])
    expect(widths(1)).toEqual(['58%', '48%', '40%', '66%'])
    expect(widths(4)).toEqual(widths(0))
  })

  it('renders for a negative or fractional variant too', () => {
    expect(() => render(<SkeletonRow variant={-1} />)).not.toThrow()
    expect(() => render(<SkeletonRow variant={1.5} />)).not.toThrow()
  })
})
