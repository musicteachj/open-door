import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { TourRing } from './tour-ring'

describe('TourRing', () => {
  it('draws a 2 px primary outline 4 px outside the target, with the target radius plus 4', () => {
    const { container } = render(
      <TourRing rect={{ x: 100, y: 200, width: 300, height: 40 }} radius={10} />,
    )
    const ring = container.firstElementChild as HTMLElement
    expect(ring).toHaveStyle({ left: '96px', top: '196px', width: '308px', height: '48px' })
    expect(ring).toHaveStyle({ borderRadius: '14px' })
    expect(ring).toHaveClass('outline-2', 'outline-primary', 'pointer-events-none')
  })

  it('is hidden from assistive technology and from the pointer', () => {
    const { container } = render(<TourRing rect={{ x: 0, y: 0, width: 10, height: 10 }} />)
    expect(container.firstElementChild).toHaveAttribute('aria-hidden', 'true')
  })

  it('defaults the target radius to 8 px', () => {
    const { container } = render(<TourRing rect={{ x: 0, y: 0, width: 10, height: 10 }} />)
    expect(container.firstElementChild).toHaveStyle({ borderRadius: '12px' })
  })

  it('is fixed to the window unless it is told to sit inside a positioned box', () => {
    const rect = { x: 0, y: 0, width: 10, height: 10 }
    const { container, rerender } = render(<TourRing rect={rect} />)
    expect(container.firstElementChild).toHaveClass('fixed')
    rerender(<TourRing rect={rect} position="absolute" />)
    expect(container.firstElementChild).toHaveClass('absolute')
  })

  it('draws nothing without a target', () => {
    const { container } = render(<TourRing rect={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
