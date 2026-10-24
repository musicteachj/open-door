import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PRIYA_WAITING, TIME_ZONE, TODAY, ZARA_WAITING } from '@/app/gallery/fixtures/timeoff'
import { ApprovalCard } from './approval-card'

function card(ui: React.ReactElement) {
  return render(<ul>{ui}</ul>)
}

const base = { today: TODAY, timeZone: TIME_ZONE }

describe('ApprovalCard, default', () => {
  it('shows the person, the sent date, the dates, the amount, the balance, and coverage', () => {
    card(
      <ApprovalCard
        request={ZARA_WAITING}
        {...base}
        onApprove={vi.fn<() => void>()}
        onDeny={vi.fn<() => void>()}
      />,
    )
    const item = screen.getByRole('listitem')
    expect(
      within(item).getByRole('heading', { level: 3, name: 'Zara Bautista' }),
    ).toBeInTheDocument()
    expect(within(item).getByText('Department Lead, Apparel')).toBeInTheDocument()
    expect(within(item).getByText('Sent October 17')).toBeInTheDocument()
    expect(within(item).getByText('Monday, November 9 to Tuesday, November 10')).toHaveClass(
      'font-semibold',
    )
    expect(within(item).getByText('PTO · 16 hours (2 days)')).toBeInTheDocument()
    expect(within(item).getByText('62 hours (7.75 days) available after this')).toBeInTheDocument()
    expect(
      within(item).getByText('Also off: Vikram Morales, Tuesday, November 10 · PTO'),
    ).toBeInTheDocument()
  })

  it('says Sent today for a request made today', () => {
    card(
      <ApprovalCard
        request={PRIYA_WAITING}
        {...base}
        onApprove={vi.fn<() => void>()}
        onDeny={vi.fn<() => void>()}
      />,
    )
    expect(screen.getByText('Sent today')).toBeInTheDocument()
    expect(screen.getByText('No one else on your team is off that day.')).toBeInTheDocument()
  })

  it('has Approve first and Deny second, both secondary and the same size, named for the request', () => {
    card(
      <ApprovalCard
        request={ZARA_WAITING}
        {...base}
        onApprove={vi.fn<() => void>()}
        onDeny={vi.fn<() => void>()}
      />,
    )
    const buttons = screen.getAllByRole('button')
    expect(buttons.map((button) => button.getAttribute('aria-label'))).toEqual([
      'Approve Zara Bautista’s PTO, November 9 to 10',
      'Deny Zara Bautista’s PTO, November 9 to 10',
    ])
    expect(buttons.map((button) => button.textContent)).toEqual(['Approve', 'Deny'])
    const [approve, deny] = buttons
    expect(approve!.className).toBe(deny!.className)
    expect(approve).toHaveClass('bg-surface-raised', 'border-border-strong')
    expect(approve).not.toHaveClass('bg-primary')
  })

  it('calls back with the request, and gives the opener the button', async () => {
    const onApprove = vi.fn<() => void>()
    const onDeny = vi.fn<() => void>()
    const user = userEvent.setup()
    card(<ApprovalCard request={ZARA_WAITING} {...base} onApprove={onApprove} onDeny={onDeny} />)
    await user.click(screen.getByRole('button', { name: /^Approve/ }))
    await user.click(screen.getByRole('button', { name: /^Deny/ }))
    expect(onApprove).toHaveBeenCalledWith(ZARA_WAITING, expect.any(HTMLButtonElement))
    expect(onDeny).toHaveBeenCalledWith(ZARA_WAITING, expect.any(HTMLButtonElement))
  })

  it('has a 40 px avatar, and stacks with half-width buttons on a phone', () => {
    card(
      <ApprovalCard
        request={ZARA_WAITING}
        {...base}
        onApprove={vi.fn<() => void>()}
        onDeny={vi.fn<() => void>()}
      />,
    )
    const item = screen.getByRole('listitem')
    expect(item.querySelector('[data-slot="avatar"]')).toHaveAttribute('data-size', 'lg')
    expect(screen.getByRole('button', { name: /^Approve/ }).parentElement!.className).toContain(
      'max-sm:grid-cols-2',
    )
    expect(item.className).toContain('max-sm:p-4')
  })
})

describe('ApprovalCard, conflict', () => {
  it('is muted, shows the Canceled badge in place of the sent date, and has no buttons', () => {
    card(<ApprovalCard request={ZARA_WAITING} {...base} conflict="canceled" />)
    const item = screen.getByRole('listitem')
    expect(item).toHaveClass('bg-surface-sunken')
    expect(within(item).getByText('Canceled')).toBeInTheDocument()
    expect(within(item).queryByText('Sent October 17')).not.toBeInTheDocument()
    expect(within(item).queryByRole('button')).not.toBeInTheDocument()
    expect(within(item).getByText('Zara Bautista')).toHaveClass('text-ink-muted')
  })

  it('keeps the hairline between the head and the body', () => {
    card(<ApprovalCard request={ZARA_WAITING} {...base} conflict="canceled" />)
    const body = screen.getByText('PTO · 16 hours (2 days)').closest('div[class*="border-t"]')!
    expect(body).toHaveClass('border-t', 'border-border-subtle')
    expect(body.parentElement).toBe(screen.getByRole('listitem'))
  })

  it('shows the refusal as an alert, without a pronoun', () => {
    const view = (conflict?: 'canceled') => (
      <ul>
        <ApprovalCard request={ZARA_WAITING} {...base} conflict={conflict} />
      </ul>
    )
    const { rerender } = render(view())
    rerender(view('canceled'))
    expect(screen.getByRole('alert')).toHaveTextContent('Zara canceled this request.')
  })

  it('does not announce a conflict that is there when the card first appears', () => {
    card(<ApprovalCard request={ZARA_WAITING} {...base} conflict="canceled" />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByText('Zara canceled this request.')).toBeInTheDocument()
  })

  it('shows an already-decided request with its own status', () => {
    card(<ApprovalCard request={ZARA_WAITING} {...base} conflict="approved" />)
    expect(screen.getByText('This request was already approved.')).toBeInTheDocument()
    expect(screen.getByText('Approved')).toBeInTheDocument()
  })
})

describe('ApprovalCard, loading', () => {
  it('is hidden skeletons', () => {
    card(<ApprovalCard loading />)
    const item = screen.getByRole('listitem', { hidden: true })
    expect(item).toHaveAttribute('aria-hidden', 'true')
    expect(item.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(3)
    expect(item).toHaveTextContent('')
  })

  describe('ApprovalCard, team coverage that may be unknown', () => {
    const asRequest = (coverage: typeof ZARA_WAITING.coverage) => ({ ...ZARA_WAITING, coverage })

    it('shows no coverage block at all when the API left it out', () => {
      card(<ApprovalCard request={asRequest(null)} {...base} />)
      expect(screen.queryByText('Team coverage')).not.toBeInTheDocument()
      expect(screen.queryByText(/No one else on your team/)).not.toBeInTheDocument()
    })

    it('says no one else is off only for an empty list', () => {
      card(<ApprovalCard request={asRequest([])} {...base} />)
      expect(screen.getByText('No one else on your team is off those days.')).toBeInTheDocument()
    })

    it('names a colleague who is off', () => {
      card(<ApprovalCard request={ZARA_WAITING} {...base} />)
      expect(screen.getByText(/^Also off: Vikram Morales/)).toBeInTheDocument()
    })

    it('treats a missing field like null', () => {
      const { coverage: _omitted, ...rest } = ZARA_WAITING
      card(<ApprovalCard request={rest} {...base} />)
      expect(screen.queryByText('Team coverage')).not.toBeInTheDocument()
    })
  })

  describe('ApprovalCard, a conflict that arrives after the skeleton', () => {
    it('does not announce a card that went from loading straight to a conflict', () => {
      const view = (ui: React.ReactElement) => <ul>{ui}</ul>
      const { rerender } = render(view(<ApprovalCard loading />))
      rerender(view(<ApprovalCard request={ZARA_WAITING} {...base} conflict="canceled" />))
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      expect(screen.getByText('Zara canceled this request.')).toBeInTheDocument()
    })

    it('announces a card that was waiting and then turned into a conflict', () => {
      const view = (conflict?: 'canceled') => (
        <ul>
          <ApprovalCard request={ZARA_WAITING} {...base} conflict={conflict} />
        </ul>
      )
      const { rerender } = render(view())
      rerender(view('canceled'))
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })
})
