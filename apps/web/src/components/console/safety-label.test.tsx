import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { InjectionTag, SafetyLabel } from './safety-label'

describe('SafetyLabel', () => {
  it('shows "Ordinary" with a hidden shield-check icon', () => {
    const { container } = render(<SafetyLabel category="ordinary" />)
    expect(screen.getByText('Ordinary')).toBeInTheDocument()
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
    expect(container.querySelector('svg')).toHaveClass('text-ink-muted')
  })

  it('adds the time when it has one', () => {
    render(<SafetyLabel category="ordinary" ms={980} />)
    expect(screen.getByText('· 980 ms')).toBeInTheDocument()
  })

  it('shows the injection tag in words, never as an alert', () => {
    const { container } = render(<SafetyLabel category="ordinary" injection />)
    expect(container).toHaveTextContent('Possible prompt injection')
    expect(container.querySelector('[role="alert"]')).toBeNull()
    expect(container.innerHTML).not.toMatch(/danger|warning/)
  })

  it('stacks the tag on two lines beside a docked panel', () => {
    const { container } = render(<InjectionTag stacked />)
    expect(container.firstElementChild).toHaveClass('flex-col')
  })

  it('shows a dash with a hidden "None" for a turn that was not screened', () => {
    const { container } = render(<SafetyLabel category={null} />)
    expect(screen.getByText('None')).toHaveClass('sr-only')
    expect(container.querySelector('[aria-hidden="true"]')).toHaveTextContent('–')
    expect(screen.queryByText('Ordinary')).not.toBeInTheDocument()
  })
})
