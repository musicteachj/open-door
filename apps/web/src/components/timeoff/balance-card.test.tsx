import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import {
  PTO_BALANCE,
  PTO_BALANCE_CEILING,
  PTO_BALANCE_EMPTY,
  PTO_RULE,
  SICK_RULE,
  SICK_YEAR,
} from '@/app/gallery/fixtures/timeoff'
import { renderWithRouter } from '@/test/render-with-router'
import { BalanceCard } from './balance-card'
import { sickCardLabel } from './labels'

function ledger(name: string) {
  const list = screen.getByRole('region', { name }).querySelector('dl')!
  return [...list.querySelectorAll('div')].map((row) => [
    row.querySelector('dt')!.textContent,
    row.querySelector('dd')!.textContent,
  ])
}

describe('BalanceCard, PTO', () => {
  it('is a region named by its label, with the rule chip under it', () => {
    renderWithRouter(<BalanceCard kind="pto" balance={PTO_BALANCE} rule={PTO_RULE} />)
    const card = screen.getByRole('region', { name: 'PTO available' })
    expect(
      within(card).getByRole('heading', { level: 2, name: 'PTO available' }),
    ).toBeInTheDocument()
    expect(
      within(card).getByRole('link', { name: 'Source: Handbook §4.1, Paid time off' }),
    ).toBeInTheDocument()
  })

  it('shows the available hours large and the days beside it, split from the API label', () => {
    renderWithRouter(<BalanceCard kind="pto" balance={PTO_BALANCE} rule={PTO_RULE} />)
    const figure = document.querySelector('[data-slot="balance-figure"]')!
    expect(figure).toHaveClass('tabular-nums')
    const big = within(figure as HTMLElement).getByText('92 hours')
    expect(big).toHaveClass('text-[40px]/12', 'font-semibold')
    const days = screen.getByText('11.5 days')
    expect(days).toHaveClass('text-body-lg', 'text-ink-muted')
  })

  it('lists the ledger with each label’s hours and no days', () => {
    renderWithRouter(<BalanceCard kind="pto" balance={PTO_BALANCE} rule={PTO_RULE} />)
    expect(ledger('PTO available')).toEqual([
      ['Earned to date', '132 hours'],
      ['Taken', '32 hours'],
      ['Booked', '8 hours'],
      ['Waiting for approval', '0 hours'],
    ])
  })

  it('says what comes next and what can be saved', () => {
    renderWithRouter(<BalanceCard kind="pto" balance={PTO_BALANCE} rule={PTO_RULE} />)
    expect(screen.getByText('Next: 10 hours on October 31')).toBeInTheDocument()
    expect(screen.getByText('You can save up to 180 hours.')).toBeInTheDocument()
    expect(screen.queryByText(/paused/i)).not.toBeInTheDocument()
  })

  it('shows the notice and the paused line when the API says earning is paused', () => {
    renderWithRouter(<BalanceCard kind="pto" balance={PTO_BALANCE_CEILING} rule={PTO_RULE} />)
    expect(screen.getByText('172 hours')).toBeInTheDocument()
    expect(screen.getByText('21.5 days')).toBeInTheDocument()
    expect(
      screen.getByText(
        'You’ve saved 180 hours, the most you can hold, so you won’t earn more PTO until you take some time off.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('Next: paused at the 180-hour limit')).toBeInTheDocument()
    expect(screen.queryByText(/You can save up to/)).not.toBeInTheDocument()
    expect(screen.queryByText(/^Next: 0/)).not.toBeInTheDocument()
  })

  it('shows the empty-history figures as they come', () => {
    renderWithRouter(<BalanceCard kind="pto" balance={PTO_BALANCE_EMPTY} rule={PTO_RULE} />)
    const figure = document.querySelector('[data-slot="balance-figure"]') as HTMLElement
    expect(within(figure).getByText('132 hours')).toBeInTheDocument()
    expect(within(figure).getByText('16.5 days')).toBeInTheDocument()
    expect(ledger('PTO available')[1]).toEqual(['Taken', '0 hours'])
  })

  it('has no figure arithmetic: every number on the card is from the labels it was given', () => {
    const { container } = renderWithRouter(
      <BalanceCard kind="pto" balance={PTO_BALANCE} rule={PTO_RULE} />,
    )
    const numbers = (container.textContent ?? '').match(/\d+(\.\d+)?/g) ?? []
    const allowed = JSON.stringify(PTO_BALANCE) + 'Handbook §4.1'
    for (const number of numbers) expect(allowed).toContain(number)
  })
})

describe('BalanceCard, sick leave', () => {
  it('shows the year’s figure, ledger, and renewal', () => {
    renderWithRouter(<BalanceCard kind="sick" year={SICK_YEAR} rule={SICK_RULE} />)
    expect(
      screen.getByRole('heading', { name: 'Sick leave available this year' }),
    ).toBeInTheDocument()
    const figure = document.querySelector('[data-slot="balance-figure"]') as HTMLElement
    expect(figure).toHaveTextContent(/^32 hours$/)
    expect(screen.queryByText('4 days')).not.toBeInTheDocument()
    expect(ledger('Sick leave available this year')).toEqual([
      ['Granted on January 1', '40 hours'],
      ['Used', '8 hours'],
      ['Booked', '0 hours'],
    ])
    expect(screen.getByText('Renews January 1.')).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Source: Handbook CA-4.3, Sick leave' }),
    ).toBeInTheDocument()
  })
})

describe('BalanceCard, a later sick year', () => {
  it('can be named for its year, so next year’s grant is not "this year"', () => {
    renderWithRouter(
      <BalanceCard
        kind="sick"
        year={SICK_YEAR}
        rule={SICK_RULE}
        label={sickCardLabel(2027, 2026)}
      />,
    )
    expect(
      screen.getByRole('heading', { name: 'Sick leave available in 2027' }),
    ).toBeInTheDocument()
  })
})

describe('sickCardLabel', () => {
  it('says "this year" for the current year and the year for another', () => {
    expect(sickCardLabel(2026, 2026)).toBe('Sick leave available this year')
    expect(sickCardLabel(2027, 2026)).toBe('Sick leave available in 2027')
  })
})

describe('BalanceCard, loading', () => {
  it('is hidden skeletons with no text', () => {
    const { container } = render(<BalanceCard kind="loading" />)
    expect(container.firstElementChild).toHaveAttribute('aria-hidden', 'true')
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(3)
    expect(container).toHaveTextContent('')
  })
})
