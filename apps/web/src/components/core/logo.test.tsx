import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Logo } from './logo'

describe('Logo', () => {
  it('shows the product name', () => {
    render(<Logo />)
    expect(screen.getByText('Open Door')).toBeInTheDocument()
  })

  it('shows the customer name under it when given one', () => {
    render(<Logo customerName="Juniper Row" />)
    expect(screen.getByText('Juniper Row')).toBeInTheDocument()
  })

  it('shows no customer name before sign-in', () => {
    const { container } = render(<Logo />)
    expect(container).toHaveTextContent(/^Open Door$/)
  })

  it('draws the door-ajar mark: the tile, the doorway, and the open door, in theme colors', () => {
    const { container } = render(<Logo />)
    const svg = container.querySelector('svg')!
    // The design's mark (docs/design/system/assets/logo-mark.svg), on the 32 px grid.
    expect(svg.querySelector('rect')).toHaveClass('fill-primary')
    const [doorway, door] = Array.from(svg.querySelectorAll('path'))
    expect(doorway).toHaveAttribute('d', 'M9 8H20a3 3 0 0 1 3 3V32H9z')
    expect(doorway).toHaveClass('fill-surface')
    expect(door).toHaveAttribute('d', 'M11 10L17.5 12.5V29.5L11 32z')
    expect(door).toHaveClass('fill-primary')
  })

  it('hides the mark from screen readers, so the name is read once', () => {
    const { container } = render(<Logo customerName="Juniper Row" />)
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
    expect(container).toHaveTextContent('Open Door Juniper Row')
  })
})
