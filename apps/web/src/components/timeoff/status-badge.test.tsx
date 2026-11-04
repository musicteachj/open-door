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

  it.each([
    ['case-sent', 'Sent to HR', 'text-marker'],
    ['case-reviewing', 'HR is reviewing', 'text-primary'],
    ['case-finished', 'HR has finished its review', 'text-ink'],
    ['case-in-review', 'In review', 'text-primary'],
    ['case-closed', 'Closed', 'text-ink'],
  ] as const)('shows the case status %s as "%s" with an icon in %s', (status, word, iconClass) => {
    render(<StatusBadge status={status} />)
    const badge = screen.getByText(word)
    const icon = badge.querySelector('svg')
    expect(icon).toHaveAttribute('aria-hidden', 'true')
    expect(icon).toHaveClass(iconClass)
    expect(badge).toHaveClass('h-6', 'border-border-strong', 'text-ink')
  })

  it('shows a new case as a small filled cinnamon dot beside the word', () => {
    render(<StatusBadge status="case-new" />)
    const badge = screen.getByText('New')
    expect(badge.querySelector('svg')).toBeNull()
    const dot = badge.querySelector('[data-slot="status-dot"]')
    expect(dot).toHaveAttribute('aria-hidden', 'true')
    expect(dot).toHaveClass('bg-marker', 'rounded-full')
  })

  it('never uses a warning color for a case status', () => {
    for (const status of ['case-new', 'case-sent', 'case-in-review', 'case-closed'] as const) {
      const { container, unmount } = render(<StatusBadge status={status} />)
      expect(container.innerHTML).not.toMatch(/danger|warning/)
      unmount()
    }
  })

  it('passes a class through', () => {
    render(<StatusBadge status="recorded" className="self-start" />)
    expect(screen.getByText('Recorded')).toHaveClass('self-start')
  })
})

describe('StatusBadge outcomes', () => {
  it.each([
    ['outcome-answered', 'Answered'],
    ['outcome-not-covered', 'Said the handbook doesn’t cover it'],
    ['outcome-refused', 'Refused by the model'],
    ['outcome-stopped', 'Stopped by the person'],
    ['outcome-failed', 'Failed'],
    ['outcome-cap', 'Spending cap reached'],
    ['outcome-safety-unavailable', 'Safety check unavailable'],
  ] as const)('shows %s as "%s" with a hidden icon', (status, word) => {
    render(<StatusBadge status={status} />)
    expect(screen.getByText(word).querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
  })

  it('uses the danger color only on Failed; every other icon is ink-muted', () => {
    const { container } = render(
      <>
        <StatusBadge status="outcome-failed" />
        <StatusBadge status="outcome-answered" />
        <StatusBadge status="outcome-refused" />
      </>,
    )
    const icons = [...container.querySelectorAll('svg')]
    expect(icons[0]).toHaveClass('text-danger')
    expect(icons[1]).toHaveClass('text-ink-muted')
    expect(icons[2]).toHaveClass('text-ink-muted')
  })
})
