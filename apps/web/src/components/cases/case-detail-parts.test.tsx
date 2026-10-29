import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CaseDetailHeader } from './case-detail-header'
import { CaseOwnNotice } from './case-own-notice'
import { CasePersonCard } from './case-person-card'

const HEADER = {
  category: 'harassment_discrimination',
  status: 'new',
  sentAt: '2026-10-26T16:41:00Z',
  replyBy: '2026-10-28',
  statusChangedAt: '2026-10-26T16:41:00Z',
  timeZone: 'America/Denver',
  today: '2026-10-26',
  crisis: false,
  isOwn: false,
} as const

describe('CaseDetailHeader', () => {
  it('has a focusable h1 with the category, a lock, and the HR badge', () => {
    const { container } = render(<CaseDetailHeader {...HEADER} />)
    const h1 = screen.getByRole('heading', { level: 1, name: 'Harassment or discrimination' })
    expect(h1).toHaveAttribute('tabindex', '-1')
    expect(container.querySelector('svg.text-primary')).toHaveAttribute('aria-hidden', 'true')
    expect(screen.getByText('New')).toBeInTheDocument()
  })

  it('hands the heading to the page as a ref, so focus can move to it', () => {
    let node: HTMLHeadingElement | null = null
    render(
      <CaseDetailHeader
        {...HEADER}
        headingRef={(el) => {
          node = el
        }}
      />,
    )
    expect(node).toBe(screen.getByRole('heading', { level: 1 }))
  })

  it('says when it was sent and when the reply is due', () => {
    const { container } = render(<CaseDetailHeader {...HEADER} />)
    expect(container.querySelector('[data-slot="case-dates"]')).toHaveTextContent(
      /Sent Mon, Oct 26, 10:41 AM MDT.*Reply due Wed, Oct 28/,
    )
  })

  it('reads as two facts to a screen reader: a hidden stop between them', () => {
    const { container } = render(<CaseDetailHeader {...HEADER} />)
    const line = container.querySelector('[data-slot="case-dates"]')!
    expect(line.querySelector('.sr-only')).toHaveTextContent('.')
    expect(line.textContent).toMatch(/MDT.*\.\s*Reply due Wed, Oct 28/)
  })

  it('keeps the lock beside the heading’s first line, and the badge after', () => {
    const { container } = render(<CaseDetailHeader {...HEADER} />)
    const lock = container.querySelector('svg.text-primary')!
    expect(lock).toHaveClass('shrink-0')
    expect(lock.parentElement).toContainElement(screen.getByRole('heading', { level: 1 }))
    expect(lock.parentElement).toHaveClass('items-start')
  })

  it.each([
    ['2026-10-26', 'Reply due today'],
    ['2026-10-25', 'Reply was due Sun, Oct 25'],
    ['2026-10-28', 'Reply due Wed, Oct 28'],
  ])('says "%s" the way the queue does', (replyBy, line) => {
    const { container } = render(<CaseDetailHeader {...HEADER} replyBy={replyBy} />)
    expect(container.querySelector('[data-slot="case-dates"]')!.textContent).toContain(line)
  })

  it('says since when a case is in review, and when it was closed', () => {
    const { rerender } = render(
      <CaseDetailHeader {...HEADER} status="in_review" statusChangedAt="2026-10-20T15:00:00Z" />,
    )
    expect(screen.getByText(/In review since Tue, Oct 20/)).toBeInTheDocument()
    rerender(
      <CaseDetailHeader {...HEADER} status="closed" statusChangedAt="2026-10-26T20:00:00Z" />,
    )
    expect(screen.getByText(/Closed Mon, Oct 26/)).toBeInTheDocument()
    expect(
      screen.getByText('Closed', { selector: '[data-slot="status-badge"]' }),
    ).toBeInTheDocument()
  })

  it('says the reads are recorded, and for a crisis case the safety check line', () => {
    const { container, rerender } = render(<CaseDetailHeader {...HEADER} />)
    expect(
      screen.getByText('Your reads of this case are recorded in its timeline.'),
    ).toBeInTheDocument()
    expect(screen.queryByText(/safety check/)).toBeNull()
    rerender(<CaseDetailHeader {...HEADER} crisis />)
    const fact = screen.getByText('The safety check routed this message to crisis text.')
    expect(fact.closest('p')).toHaveClass('text-ink-muted')
    expect(container.innerHTML).not.toMatch(/danger|warning/)
  })

  it('leaves out the reads line for HR’s own case', () => {
    render(<CaseDetailHeader {...HEADER} isOwn />)
    expect(screen.queryByText(/recorded in its timeline/)).toBeNull()
  })
})

describe('CasePersonCard', () => {
  const PERSON = {
    name: 'Priya Raman',
    title: 'Visual Merchandiser',
    department: 'Store Operations',
    location: 'Oakland store',
    email: 'priya.raman@juniperrow.example',
  }

  it('shows the person, their details, and a mailto link', () => {
    render(<CasePersonCard {...PERSON} />)
    expect(screen.getByText('Priya Raman')).toBeInTheDocument()
    expect(screen.getByText('PR')).toBeInTheDocument()
    expect(screen.getByText('Visual Merchandiser')).toBeInTheDocument()
    expect(screen.getByText('Department').nextElementSibling).toHaveTextContent('Store Operations')
    expect(screen.getByText('Location').nextElementSibling).toHaveTextContent('Oakland store')
    expect(screen.getByRole('link', { name: 'priya.raman@juniperrow.example' })).toHaveAttribute(
      'href',
      'mailto:priya.raman@juniperrow.example',
    )
  })

  it('says Open Door sends no messages', () => {
    render(<CasePersonCard {...PERSON} />)
    expect(
      screen.getByText('Reply by email or in person. Open Door doesn’t send messages.'),
    ).toBeInTheDocument()
  })

  it('shows a dash for a missing detail and no link without an email', () => {
    render(<CasePersonCard {...PERSON} department={null} email={null} />)
    expect(screen.getByText('Department').nextElementSibling).toHaveTextContent('-')
    expect(screen.queryByRole('link')).toBeNull()
  })
})

describe('CaseOwnNotice', () => {
  it('says the person opened it, so cannot act on it or read it here', () => {
    const { container } = render(<CaseOwnNotice />)
    expect(
      screen.getByText('You opened this case, so you can’t act on it or read it here.'),
    ).toBeInTheDocument()
    expect(container.firstElementChild).toHaveClass('bg-confidential-tint')
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
  })
})
