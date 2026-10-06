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

  it('hides the mark from screen readers, so the name is read once', () => {
    const { container } = render(<Logo customerName="Juniper Row" />)
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
    expect(container).toHaveTextContent('Open Door Juniper Row')
  })
})
