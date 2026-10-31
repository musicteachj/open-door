import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { CaseStatusOut } from '@/api/generated'
import { CaseList } from './case-list'

const TZ = 'America/Denver'

const CASES: CaseStatusOut[] = [
  {
    id: 'c1',
    category: 'harassment_discrimination',
    status: 'new',
    sentAt: '2026-10-26T16:41:00Z',
    replyBy: '2026-10-28',
    statusChangedAt: '2026-10-26T16:41:00Z',
  },
  {
    id: 'c2',
    category: 'safety',
    status: 'in_review',
    sentAt: '2026-10-12T15:00:00Z',
    replyBy: '2026-10-14',
    statusChangedAt: '2026-10-13T15:00:00Z',
  },
  {
    id: 'c3',
    category: 'pay',
    status: 'closed',
    sentAt: '2026-09-15T15:00:00Z',
    replyBy: '2026-09-17',
    statusChangedAt: '2026-09-25T15:00:00Z',
  },
]

describe('CaseList', () => {
  it('is a list named "Your cases" with a row per case', () => {
    render(<CaseList cases={CASES} timeZone={TZ} onOpenCase={() => {}} />)
    const list = screen.getByRole('list', { name: 'Your cases' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(3)
  })

  it('shows the category, the sent day, the badge, and the date line for a new case', () => {
    render(<CaseList cases={CASES} timeZone={TZ} onOpenCase={() => {}} />)
    const row = screen.getAllByRole('listitem')[0]!
    expect(within(row).getByText('Harassment or discrimination')).toHaveClass('font-semibold')
    expect(within(row).getByText('Sent Mon, Oct 26')).toBeInTheDocument()
    expect(within(row).getByText('Sent to HR')).toBeInTheDocument()
    expect(within(row).getByText('HR replies by Wed, Oct 28')).toBeInTheDocument()
  })

  it('shows "Since" for a case in review and "Finished" for a closed one', () => {
    render(<CaseList cases={CASES} timeZone={TZ} onOpenCase={() => {}} />)
    const [, review, closed] = screen.getAllByRole('listitem')
    expect(within(review!).getByText('HR is reviewing')).toBeInTheDocument()
    expect(within(review!).getByText('Since Tue, Oct 13')).toBeInTheDocument()
    expect(within(closed!).getByText('HR has finished its review')).toBeInTheDocument()
    expect(within(closed!).getByText('Finished Fri, Sep 25')).toBeInTheDocument()
  })

  it('shows a status change in the viewer’s zone, not UTC', () => {
    const late: CaseStatusOut = { ...CASES[1]!, statusChangedAt: '2026-10-14T02:00:00Z' }
    render(<CaseList cases={[late]} timeZone={TZ} onOpenCase={() => {}} />)
    expect(screen.getByText('Since Tue, Oct 13')).toBeInTheDocument()
  })

  it('has no links in a row and shows no words', () => {
    render(<CaseList cases={CASES} timeZone={TZ} onOpenCase={() => {}} />)
    expect(within(screen.getByRole('list')).queryAllByRole('link')).toHaveLength(0)
  })

  it('keeps the rows’ order as given', () => {
    render(<CaseList cases={[...CASES].reverse()} timeZone={TZ} onOpenCase={() => {}} />)
    expect(screen.getAllByRole('listitem')[0]).toHaveTextContent('Pay concern')
  })

  it('lays rows out as the design does at desktop and phone widths', () => {
    render(<CaseList cases={CASES} timeZone={TZ} onOpenCase={() => {}} />)
    const row = screen.getAllByRole('listitem')[0]!
    expect(row.className).toContain('grid-cols-[minmax(0,1fr)_248px_176px]')
    expect(row.className).toContain('max-sm:grid-cols-[minmax(0,1fr)_auto]')
  })

  it('shows the empty state with the button, and no list', async () => {
    const onOpenCase = vi.fn<() => void>()
    render(<CaseList cases={[]} timeZone={TZ} onOpenCase={onOpenCase} />)
    expect(screen.queryByRole('list')).toBeNull()
    expect(screen.getByText('You haven’t sent HR a case.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Open a confidential case' }))
    expect(onOpenCase).toHaveBeenCalledTimes(1)
  })

  it('is neutral: no danger styling anywhere', () => {
    const { container } = render(<CaseList cases={CASES} timeZone={TZ} onOpenCase={() => {}} />)
    expect(container.innerHTML).not.toMatch(/danger|warning/)
  })
})
