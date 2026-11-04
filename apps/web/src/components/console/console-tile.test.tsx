import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ConsoleTile } from './console-tile'

describe('ConsoleTile', () => {
  it('is a group named by its title', () => {
    render(<ConsoleTile title="Time to first token" figure="1.6 s" />)
    const group = screen.getByRole('group', { name: 'Time to first token' })
    expect(within(group).getByRole('heading', { level: 3 })).toHaveTextContent(
      'Time to first token',
    )
  })

  it('shows the lead-in, figure, lines, and foot', () => {
    render(
      <ConsoleTile
        title="Time to first token"
        pre="Median"
        figure="1.6 s"
        lines={['95th percentile 2.2 s', 'Target 3 s']}
        foot="9 turns · Small sample"
      />,
    )
    for (const text of [
      'Median',
      '1.6 s',
      '95th percentile 2.2 s',
      'Target 3 s',
      '9 turns · Small sample',
    ])
      expect(screen.getByText(text)).toBeInTheDocument()
  })

  it('shows rows as a list of terms and counts', () => {
    render(
      <ConsoleTile
        title="Cards confirmed by a person"
        rows={[
          ['Time-off requests', '1'],
          ['Cancellations', '0'],
        ]}
        foot="From the audit log"
      />,
    )
    expect(screen.getByText('Cancellations').closest('div')).toHaveTextContent('Cancellations0')
  })

  it('shows what search came closest with, or "None yet"', () => {
    const { rerender } = render(
      <ConsoleTile
        title="T"
        figure="2"
        closest={['4.1 Paid time off (2)', '5.2 Parental leave (1)']}
      />,
    )
    expect(screen.getByText('Search came closest with:')).toBeInTheDocument()
    expect(screen.getByText('4.1 Paid time off (2)')).toBeInTheDocument()
    rerender(<ConsoleTile title="T" figure="0" closest={[]} />)
    expect(screen.getByText('None yet')).toBeInTheDocument()
  })

  it('says "No turns yet" when empty, and keeps a spend line', () => {
    render(<ConsoleTile title="Cost" state="empty" spend="Sandbox spend $0.00 of $1.00 cap" />)
    expect(screen.getByText('No turns yet')).toBeInTheDocument()
    expect(screen.getByText('Sandbox spend $0.00 of $1.00 cap')).toBeInTheDocument()
  })

  it('keeps the title and shows hidden skeleton bars while loading', () => {
    const { container } = render(
      <ConsoleTile title="Escalation rate" state="loading" figure="11%" spend="x" />,
    )
    expect(screen.getByRole('heading', { name: 'Escalation rate' })).toBeInTheDocument()
    expect(screen.queryByText('11%')).not.toBeInTheDocument()
    expect(screen.queryByText('x')).not.toBeInTheDocument()
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0)
  })

  it('never styles a figure as a warning', () => {
    const { container } = render(
      <ConsoleTile
        title="Safety check time"
        pre="95th percentile"
        figure="980 ms"
        lines={['Target 800 ms']}
      />,
    )
    expect(container.innerHTML).not.toMatch(/danger|warning|marker|red|amber/)
  })
})
