import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SandboxIndicator } from './sandbox-indicator'

describe('SandboxIndicator', () => {
  it('renders its text', () => {
    render(<SandboxIndicator>Sandbox resets in 21 h</SandboxIndicator>)
    expect(screen.getByText('Sandbox resets in 21 h')).toBeInTheDocument()
  })

  it('hides its clock icon from screen readers', () => {
    const { container } = render(<SandboxIndicator>Sandbox resets in 21 h</SandboxIndicator>)
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
  })
})
