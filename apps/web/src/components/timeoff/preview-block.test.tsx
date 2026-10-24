import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import {
  CARD_CROSS_YEAR_SICK,
  CARD_HOLIDAY,
  CHECK_CROSS_YEAR_SICK,
  CHECK_HOLIDAY,
  CHECK_LONG_RUNS,
  CHECK_NOT_ENOUGH,
  CHECK_NOTHING_COUNTED,
  CHECK_ONE_DAY,
  CHECK_OVERLAP,
  CHECK_SICK_HOURS,
  CHECK_WEEKEND,
} from '@/app/gallery/fixtures/timeoff'
import type { CheckOut } from '@/api/generated'
import { MemoryRouter } from 'react-router'
import { renderWithRouter } from '@/test/render-with-router'
import { PreviewBlock } from './preview-block'

function block(
  check: CheckOut,
  extra: { type?: 'pto' | 'sick'; refused?: boolean; thisYear?: number } = {},
) {
  return renderWithRouter(
    <PreviewBlock
      type={extra.type ?? 'pto'}
      countedDays={check.countedDays}
      skippedDays={check.skippedDays}
      overlappingDays={check.overlappingDays}
      amountLabel={check.amountLabel}
      draws={check.draws}
      rules={check.rules}
      refused={extra.refused}
      thisYear={extra.thisYear}
    />,
  )
}

function lines(): string[] {
  return screen.getAllByRole('listitem').map((item) => item.textContent ?? '')
}

describe('PreviewBlock', () => {
  it('asks for dates when nothing is picked', () => {
    renderWithRouter(
      <PreviewBlock
        type="pto"
        countedDays={[]}
        skippedDays={[]}
        amountLabel={null}
        draws={[]}
        rules={[]}
        empty
      />,
    )
    expect(screen.getByText('Pick dates to see what this uses.')).toBeInTheDocument()
    expect(screen.queryByText('What this uses')).not.toBeInTheDocument()
  })

  it('lists one counted day with a check, the total, what is left, and the sources', () => {
    block(CHECK_ONE_DAY)
    expect(screen.getByRole('heading', { level: 3, name: 'What this uses' })).toBeInTheDocument()
    expect(lines().filter((line) => line.includes('Counted:'))).toEqual([
      'Counted: Friday, October 30',
    ])
    expect(screen.getByText('8 hours (1 day)')).toHaveClass('font-semibold')
    expect(screen.getByText(/84 hours \(10\.5 days\) left after this/)).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Source: Handbook §4.1, Paid time off' }),
    ).toBeInTheDocument()
  })

  it('shows dates only on a counted line, never hours', () => {
    block(CHECK_WEEKEND)
    const counted = screen.getAllByText(/^Counted:/).map((el) => el.closest('li')!)
    expect(counted.map((li) => li.textContent)).toEqual([
      'Counted: Friday, October 30',
      'Counted: Monday, November 2',
    ])
    for (const li of counted) expect(li.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
  })

  it('lists skipped weekend days one by one when there are two or fewer', () => {
    block(CHECK_WEEKEND)
    expect(screen.getByText('Saturday, October 31 isn’t on your schedule')).toBeInTheDocument()
    expect(screen.getByText('Sunday, November 1 isn’t on your schedule')).toBeInTheDocument()
  })

  it('names a skipped holiday and cites the holiday rule', () => {
    block(CHECK_HOLIDAY)
    expect(
      screen.getByText('Thursday, November 26 is Thanksgiving, a company holiday'),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Source: Handbook §4.2, Holidays' }),
    ).toBeInTheDocument()
  })

  it('speaks Counted and Skipped before each line, hidden from sight', () => {
    block(CHECK_HOLIDAY)
    const prefix = screen.getAllByText('Counted:')[0]!
    expect(prefix).toHaveClass('sr-only')
    expect(screen.getByText('Skipped:')).toHaveClass('sr-only')
  })

  it('is a polite live region', () => {
    block(CHECK_ONE_DAY)
    expect(document.querySelector('[aria-live="polite"]')).toContainElement(
      screen.getByText('8 hours (1 day)'),
    )
  })

  it('folds more than five counted days into runs of consecutive days', () => {
    block(CHECK_LONG_RUNS)
    const counted = screen.getAllByText(/^Counted:/).map((el) => el.closest('li')!.textContent)
    expect(counted).toEqual([
      'Counted: Monday, November 30 to Friday, December 4',
      'Counted: Monday, December 7 to Friday, December 11',
    ])
  })

  it('keeps five counted days as single lines', () => {
    block({
      ...CHECK_LONG_RUNS,
      countedDays: CHECK_LONG_RUNS.countedDays.slice(0, 5),
    })
    expect(screen.getAllByText(/^Counted:/)).toHaveLength(5)
  })

  it('folds more than two weekend days into one line', () => {
    block(CHECK_NOT_ENOUGH)
    expect(
      screen.getByText('Saturdays and Sundays in these dates aren’t on your schedule'),
    ).toBeInTheDocument()
    expect(screen.queryByText(/Saturday, December 5/)).not.toBeInTheDocument()
  })

  it('keeps a skipped holiday as its own line beside the folded days', () => {
    block({
      ...CHECK_NOT_ENOUGH,
      skippedDays: [...CHECK_NOT_ENOUGH.skippedDays, { day: '2026-12-10', reason: 'Founders Day' }],
    })
    expect(
      screen.getByText('Thursday, December 10 is Founders Day, a company holiday'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Saturdays and Sundays in these dates aren’t on your schedule'),
    ).toBeInTheDocument()
  })

  it('names only the weekdays actually skipped, in week order', () => {
    const days = (...list: string[]) => list.map((day) => ({ day, reason: 'not scheduled' }))
    // Three Sundays: Nov 1, 8, 15.
    block({ ...CHECK_LONG_RUNS, skippedDays: days('2026-11-01', '2026-11-08', '2026-11-15') })
    expect(screen.getByText('Sundays in these dates aren’t on your schedule')).toBeInTheDocument()
  })

  it('folds a schedule that is off on other days, like Monday and Tuesday', () => {
    const days = (...list: string[]) => list.map((day) => ({ day, reason: 'not scheduled' }))
    // Mondays and Tuesdays: Nov 9, 10, 16, 17, listed out of week order on purpose.
    block({
      ...CHECK_LONG_RUNS,
      skippedDays: days('2026-11-10', '2026-11-09', '2026-11-17', '2026-11-16'),
    })
    expect(
      screen.getByText('Mondays and Tuesdays in these dates aren’t on your schedule'),
    ).toBeInTheDocument()
  })

  it('lists three or more weekdays with commas', () => {
    const days = (...list: string[]) => list.map((day) => ({ day, reason: 'not scheduled' }))
    block({
      ...CHECK_LONG_RUNS,
      skippedDays: days('2026-11-09', '2026-11-10', '2026-11-11'),
    })
    expect(
      screen.getByText('Mondays, Tuesdays, and Wednesdays in these dates aren’t on your schedule'),
    ).toBeInTheDocument()
  })

  it('does not fold two or fewer not-scheduled days', () => {
    block(CHECK_WEEKEND)
    expect(screen.getByText('Saturday, October 31 isn’t on your schedule')).toBeInTheDocument()
  })

  it('shows the total without a left line when a refusal applies', () => {
    block(CHECK_NOT_ENOUGH, { refused: true })
    expect(screen.getByText('120 hours (15 days)')).toBeInTheDocument()
    expect(screen.queryByText(/left after this/)).not.toBeInTheDocument()
  })

  it('marks an already booked day and shows no total at all', () => {
    block(CHECK_OVERLAP, { refused: true })
    const item = screen.getByText('Wednesday, December 23').closest('li')!
    expect(within(item).getByText('Can’t be counted:')).toHaveClass('sr-only')
    expect(within(item).getByText('Already booked')).toBeInTheDocument()
    expect(item.querySelector('svg')).toHaveClass('text-danger')
    expect(screen.queryByText('8 hours (1 day)')).not.toBeInTheDocument()
    expect(screen.queryByText(/left after this/)).not.toBeInTheDocument()
  })

  it('says nothing can be requested when no day counts', () => {
    block(CHECK_NOTHING_COUNTED, { refused: true })
    expect(
      screen.getByText('None of these days are on your schedule, so there’s nothing to request.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Saturday, October 31 isn’t on your schedule')).toBeInTheDocument()
    expect(screen.queryByText('Counted:')).not.toBeInTheDocument()
  })

  it('says sick leave left this year, in hours', () => {
    block(CHECK_SICK_HOURS, { type: 'sick' })
    expect(screen.getByText('3 hours')).toBeInTheDocument()
    expect(screen.getByText(/29 hours of sick leave left this year/)).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Source: Handbook CA-4.3, Sick leave' }),
    ).toBeInTheDocument()
  })

  it('gives one left line per year for sick time across New Year', () => {
    block(CHECK_CROSS_YEAR_SICK, { type: 'sick', thisYear: 2026 })
    expect(screen.getByText('24 hours (3 days)')).toBeInTheDocument()
    expect(
      screen.getByText("Friday, January 1 is New Year's Day, a company holiday"),
    ).toBeInTheDocument()
    expect(screen.getByText('16 hours of sick leave left in 2026')).toBeInTheDocument()
    expect(screen.getByText('32 hours of sick leave left in 2027')).toBeInTheDocument()
  })

  it('takes a request card’s fields as well as the check route’s', () => {
    renderWithRouter(
      <PreviewBlock
        type={CARD_HOLIDAY.type}
        countedDays={CARD_HOLIDAY.countedDays}
        skippedDays={CARD_HOLIDAY.skippedDays}
        amountLabel={CARD_HOLIDAY.amountLabel}
        draws={CARD_HOLIDAY.draws}
        rules={CARD_HOLIDAY.rules}
      />,
    )
    expect(screen.getByText('16 hours (2 days)')).toBeInTheDocument()
    expect(screen.getByText(/76 hours \(9\.5 days\) left after this/)).toBeInTheDocument()
    expect(CARD_CROSS_YEAR_SICK.draws).toHaveLength(2)
  })

  it('mutes its text and check marks when asked, for a card that ended without a change', () => {
    const { container } = renderWithRouter(
      <PreviewBlock
        type="pto"
        countedDays={CHECK_ONE_DAY.countedDays}
        skippedDays={[]}
        amountLabel={CHECK_ONE_DAY.amountLabel}
        draws={CHECK_ONE_DAY.draws}
        rules={CHECK_ONE_DAY.rules}
        muted
      />,
    )
    expect(container.querySelector('[data-slot="preview-block"]')).toHaveClass('text-ink-muted')
    expect(container.querySelector('li svg')).toHaveClass('text-ink-muted')
  })

  it('keeps one live region mounted from the empty line to the first preview', () => {
    const empty = (
      <PreviewBlock
        type="pto"
        countedDays={[]}
        skippedDays={[]}
        amountLabel={null}
        draws={[]}
        rules={[]}
        empty
      />
    )
    const filled = (
      <PreviewBlock
        type="pto"
        countedDays={CHECK_ONE_DAY.countedDays}
        skippedDays={[]}
        amountLabel={CHECK_ONE_DAY.amountLabel}
        draws={CHECK_ONE_DAY.draws}
        rules={CHECK_ONE_DAY.rules}
      />
    )
    const { container, rerender } = renderWithRouter(empty)
    const live = container.querySelector('[aria-live="polite"]')!
    expect(live).toHaveTextContent('Pick dates to see what this uses.')
    rerender(<MemoryRouter>{filled}</MemoryRouter>)
    expect(container.querySelector('[aria-live="polite"]')).toBe(live)
    expect(live).toHaveTextContent('Counted: Friday, October 30')
  })
})
