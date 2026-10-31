import { screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { QueueItemOut } from '@/api/generated'
import { arrow } from '@/test/arrow-key'
import { renderWithRouter } from '@/test/render-with-router'
import { CaseQueueTable, type CaseQueueTableProps } from './case-queue-table'

const TZ = 'America/Denver'

function row(overrides: Partial<QueueItemOut>): QueueItemOut {
  return {
    id: 'c-priya',
    category: 'harassment_discrimination',
    personId: 'p1',
    givenName: 'Priya',
    familyName: 'Raman',
    title: 'Visual Merchandiser',
    locationName: 'Oakland store',
    sentAt: '2026-10-26T16:41:00Z',
    replyBy: '2026-10-28',
    status: 'new',
    statusChangedAt: '2026-10-26T16:41:00Z',
    crisis: false,
    isOwn: false,
    ...overrides,
  }
}

function setup(props: Partial<CaseQueueTableProps> = {}) {
  const onFilterChange = vi.fn<(filter: string) => void>()
  const view = renderWithRouter(
    <CaseQueueTable
      rows={[row({})]}
      filter="open"
      onFilterChange={onFilterChange}
      today="2026-10-26"
      timeZone={TZ}
      {...props}
    />,
  )
  return { ...view, onFilterChange }
}

describe('CaseQueueTable', () => {
  it('shows a link per case to its detail, named by the facts in order', () => {
    setup()
    const link = screen.getByRole('link', {
      name: 'Priya Raman, Visual Merchandiser, Oakland store. Harassment or discrimination. Sent Mon, Oct 26. Reply due Wed, Oct 28. New.',
    })
    expect(link).toHaveAttribute('href', '/cases/c-priya')
  })

  it('has a list named Cases and the column labels, hidden from assistive technology', () => {
    setup()
    expect(screen.getByRole('list', { name: 'Cases' })).toBeInTheDocument()
    const header = screen.getByText('Person').parentElement!
    expect(header).toHaveAttribute('aria-hidden', 'true')
    expect(header.textContent).toBe('PersonCategorySentReplyStatus')
    expect(header).toHaveClass('max-sm:hidden')
  })

  it('shows the person, the category, the sent date, the reply line, and the badge', () => {
    setup()
    const item = screen.getByRole('link')
    expect(within(item).getByText('Priya Raman')).toBeInTheDocument()
    expect(within(item).getByText('Visual Merchandiser · Oakland store')).toBeInTheDocument()
    expect(within(item).getByText('PR')).toBeInTheDocument()
    expect(within(item).getByText('Harassment or discrimination')).toBeInTheDocument()
    expect(within(item).getByText('Mon, Oct 26')).toBeInTheDocument()
    expect(within(item).getByText('Reply due Wed, Oct 28')).toBeInTheDocument()
    expect(within(item).getByText('New')).toBeInTheDocument()
  })

  it.each([
    ['2026-10-26', 'Reply due today'],
    ['2026-10-28', 'Reply due Wed, Oct 28'],
    ['2026-10-25', 'Reply was due Sun, Oct 25'],
  ])('a new case with reply-by %s reads "%s" when today is Oct 26', (replyBy, line) => {
    setup({ rows: [row({ replyBy })] })
    expect(screen.getByText(line)).toBeInTheDocument()
  })

  it('compares calendar dates, so the time zone cannot move "today"', () => {
    // The reply-by date is Oct 26 and today is Oct 26, whatever the zone or the clock says.
    setup({
      rows: [row({ replyBy: '2026-10-26' })],
      today: '2026-10-26',
      timeZone: 'Pacific/Auckland',
    })
    expect(screen.getByText('Reply due today')).toBeInTheDocument()
  })

  it('reads the reply line for a case in review and a closed one', () => {
    setup({
      rows: [
        row({ id: 'a', status: 'in_review', statusChangedAt: '2026-10-20T15:00:00Z' }),
        row({ id: 'b', status: 'closed', statusChangedAt: '2026-10-16T15:00:00Z' }),
      ],
    })
    expect(screen.getByText('In review since Tue, Oct 20')).toBeInTheDocument()
    expect(screen.getByText('Closed Fri, Oct 16')).toBeInTheDocument()
    const list = within(screen.getByRole('list', { name: 'Cases' }))
    expect(list.getByText('In review')).toBeInTheDocument()
    expect(list.getByText('Closed')).toBeInTheDocument()
  })

  it('shows the crisis fact under the category, in the name too, in muted ink', () => {
    setup({ rows: [row({ crisis: true })] })
    const fact = screen.getByText('The safety check routed this message to crisis text.')
    expect(fact.closest('span')).toHaveClass('text-ink-muted')
    expect(fact.parentElement!.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
    expect(screen.getByRole('link').getAttribute('aria-label')).toContain(
      'Harassment or discrimination. The safety check routed this message to crisis text. Sent',
    )
  })

  it('shows no crisis fact when there is none, including on HR’s own case', () => {
    setup({ rows: [row({ crisis: null, isOwn: true })] })
    expect(screen.queryByText(/safety check/)).toBeNull()
    // Read-only means no action on the row, but it still links to its own-case view.
    expect(screen.getByRole('link')).toHaveAttribute('href', '/cases/c-priya')
  })

  it('never styles an overdue reply or the crisis fact as an error or a warning', () => {
    const { container } = setup({
      rows: [row({ replyBy: '2026-10-20', crisis: true })],
    })
    expect(screen.getByText('Reply was due Tue, Oct 20')).toBeInTheDocument()
    expect(container.innerHTML).not.toMatch(/danger|warning|text-red|bg-red/)
  })

  it('keeps the rows in the order given', () => {
    setup({ rows: [row({ id: 'z', givenName: 'Zed' }), row({ id: 'a', givenName: 'Abe' })] })
    const links = screen.getAllByRole('link')
    expect(links[0]).toHaveAttribute('href', '/cases/z')
    expect(links[1]).toHaveAttribute('href', '/cases/a')
  })

  it('has a "Show" filter that is one tab stop and moves with the arrow keys', async () => {
    const { user, onFilterChange } = setup()
    const group = screen.getByRole('radiogroup', { name: 'Show' })
    const options = within(group).getAllByRole('radio')
    expect(options.map((o) => o.textContent)).toEqual(['Open', 'New', 'In review', 'Closed', 'All'])
    expect(screen.getByRole('radio', { name: 'Open' })).toBeChecked()
    await user.tab()
    expect(screen.getByRole('radio', { name: 'Open' })).toHaveFocus()
    await arrow(user, 'ArrowRight')
    expect(onFilterChange).toHaveBeenCalledWith('new')
    await user.tab()
    expect(screen.getByRole('link')).toHaveFocus()
  })

  it.each([
    ['open', 'No open cases.'],
    ['new', 'No new cases. A case appears here as soon as someone sends one.'],
    ['in_review', 'No cases in review.'],
    ['closed', 'No closed cases.'],
    ['all', 'No cases yet.'],
  ] as const)('says "%s" is empty with "%s"', (filter, text) => {
    setup({ rows: [], filter })
    expect(screen.getByRole('status')).toHaveTextContent(text)
    expect(screen.queryByRole('list')).toBeNull()
  })

  it('stacks on a phone: no sent date or chevron, the reply line and badge on one line', () => {
    setup()
    const link = screen.getByRole('link')
    expect(link.className).toContain('max-sm:grid-cols-[minmax(0,1fr)_auto]')
    expect(screen.getByText('Mon, Oct 26')).toHaveClass('max-sm:hidden')
    expect(link.querySelector('[data-slot="chevron"]')).toHaveClass('max-sm:hidden')
  })

  it('uses the design’s columns and row height on a wide screen', () => {
    setup()
    const link = screen.getByRole('link')
    expect(link.className).toContain(
      'grid-cols-[minmax(0,2.5fr)_minmax(0,2fr)_minmax(0,1fr)_minmax(0,1.6fr)_120px_16px]',
    )
    expect(link).toHaveClass('min-h-16', 'gap-x-6')
  })

  it('holds no words or summary: a row only knows facts', () => {
    const keys = Object.keys(row({}))
    expect(keys).not.toContain('text')
    expect(keys).not.toContain('summary')
    expect(keys).not.toContain('words')
  })
})
