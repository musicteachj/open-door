import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { FormMessage } from './form-message'

describe('FormMessage', () => {
  it('is a polite status for a warning, on the warning tint with ink text', () => {
    render(
      <FormMessage tone="warning">More than 3 days usually needs 2 weeks’ notice.</FormMessage>,
    )
    const message = screen.getByRole('status')
    expect(message).toHaveTextContent('More than 3 days usually needs 2 weeks’ notice.')
    expect(message).toHaveClass('bg-warning-tint', 'border-warning-border')
    expect(message.querySelector('p')).toHaveClass('text-ink')
    expect(message.querySelector('svg')).toHaveClass('text-warning')
    expect(message.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
  })

  it('is an alert for a refusal, on the danger tint with ink text', () => {
    render(<FormMessage tone="refusal">You have 92 hours available.</FormMessage>)
    const message = screen.getByRole('alert')
    expect(message).toHaveTextContent('You have 92 hours available.')
    expect(message).toHaveClass('bg-danger-tint', 'border-danger-border')
    expect(message.querySelector('p')).toHaveClass('text-ink')
    expect(message.querySelector('svg')).toHaveClass('text-danger')
  })

  it('uses a different icon for each tone', () => {
    const { container, rerender } = render(<FormMessage tone="warning">A</FormMessage>)
    const warning = container.querySelector('svg')?.getAttribute('class')
    rerender(<FormMessage tone="refusal">A</FormMessage>)
    expect(container.querySelector('svg')?.getAttribute('class')).not.toBe(warning)
  })
})
