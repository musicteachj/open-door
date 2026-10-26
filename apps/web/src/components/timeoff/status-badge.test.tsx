import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RequestOutStatus } from '@/api/generated'
import { StatusBadge } from './status-badge'

describe('StatusBadge', () => {
  it.each([
    ['waiting', 'Waiting for approval', 'text-marker'],
    ['approved', 'Approved', 'text-success'],
    ['denied', 'Denied', 'text-ink'],
    ['recorded', 'Recorded', 'text-success'],
    ['canceled', 'Canceled', 'text-ink-muted'],
  ] as const)('shows %s as "%s" with an icon in %s', (status, word, iconClass) => {
    render(<StatusBadge status={status} />)
    const badge = screen.getByText(word)
    expect(badge).toBeInTheDocument()
    const icon = badge.querySelector('svg')
    expect(icon).toHaveAttribute('aria-hidden', 'true')
    expect(icon).toHaveClass(iconClass)
  })

  it('is a 24 px chip with a strong border and small medium text', () => {
    render(<StatusBadge status="approved" />)
    expect(screen.getByText('Approved')).toHaveClass(
      'h-6',
      'border-border-strong',
      'rounded-xs',
      'text-small',
      'font-medium',
      'text-ink',
    )
  })

  it('never uses the danger color, even for a denial', () => {
    render(<StatusBadge status="denied" />)
    const badge = screen.getByText('Denied')
    expect(badge.className).not.toMatch(/danger/)
    expect(badge.querySelector('svg')?.getAttribute('class')).not.toMatch(/danger/)
  })

  it('mutes the whole badge when the request was canceled', () => {
    render(<StatusBadge status="canceled" />)
    expect(screen.getByText('Canceled')).toHaveClass('text-ink-muted')
  })

  it('reads the API’s pending as waiting for approval', () => {
    render(<StatusBadge status={RequestOutStatus.pending} />)
    expect(screen.getByText('Waiting for approval')).toBeInTheDocument()
  })

  it('passes a class through', () => {
    render(<StatusBadge status="recorded" className="self-start" />)
    expect(screen.getByText('Recorded')).toHaveClass('self-start')
  })
})
