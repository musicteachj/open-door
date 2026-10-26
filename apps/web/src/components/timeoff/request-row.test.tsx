import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import {
  MINE_APPROVED,
  MINE_CANCELED,
  MINE_DENIED,
  MINE_RECORDED,
  MINE_WAITING,
  TEAM_APPROVED,
  TEAM_SICK,
} from '@/app/gallery/fixtures/timeoff'
import { RequestGroup } from './request-group'
import { RequestRow } from './request-row'

function inList(ui: React.ReactElement) {
  return render(<ul>{ui}</ul>)
}

describe('RequestRow, mine', () => {
  it('shows the dates over the type and amount, the badge, and who decided', () => {
    inList(<RequestRow variant="mine" request={MINE_APPROVED} />)
    const row = screen.getByRole('listitem')
    expect(within(row).getByText('Wednesday, December 23')).toHaveClass('font-semibold')
    expect(within(row).getByText('PTO · 8 hours (1 day)')).toBeInTheDocument()
    expect(within(row).getByText('Approved')).toBeInTheDocument()
    expect(within(row).getByText('Approved by Marcus Bell')).toBeInTheDocument()
  })

  it('writes a sick request as Sick time with the API label', () => {
    inList(<RequestRow variant="mine" request={MINE_RECORDED} />)
    expect(screen.getByText('Sick time · 3 hours')).toBeInTheDocument()
    expect(screen.getByText('Recorded')).toBeInTheDocument()
  })

  it('shows Waiting for approval with no decider', () => {
    inList(<RequestRow variant="mine" request={MINE_WAITING} />)
    expect(screen.getByText('Waiting for approval')).toBeInTheDocument()
    expect(screen.queryByText(/by Marcus/)).not.toBeInTheDocument()
  })

  it('writes a date range with both ends', () => {
    inList(
      <RequestRow
        variant="mine"
        request={{ ...MINE_WAITING, startDate: '2026-11-25', endDate: '2026-11-27' }}
      />,
    )
    expect(screen.getByText('Wednesday, November 25 to Friday, November 27')).toBeInTheDocument()
  })

  it('offers Cancel only when the caller says so, named for the request', async () => {
    const onCancel = vi.fn<(request: unknown, button: HTMLButtonElement) => void>()
    const user = userEvent.setup()
    const { rerender } = inList(<RequestRow variant="mine" request={MINE_APPROVED} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    rerender(
      <ul>
        <RequestRow variant="mine" request={MINE_APPROVED} canCancel onCancel={onCancel} />
      </ul>,
    )
    const button = screen.getByRole('button', { name: 'Cancel PTO on Wednesday, December 23' })
    await user.click(button)
    // The button comes too, so the page can put focus back on it.
    expect(onCancel).toHaveBeenCalledWith(MINE_APPROVED, button)
  })

  it('names a sick Cancel button for sick time', () => {
    inList(
      <RequestRow
        variant="mine"
        request={MINE_RECORDED}
        canCancel
        onCancel={vi.fn<() => void>()}
      />,
    )
    expect(
      screen.getByRole('button', { name: 'Cancel sick time on Thursday, October 22' }),
    ).toBeInTheDocument()
  })

  it('shows a denial note under the row, labeled with the decider', () => {
    inList(<RequestRow variant="mine" request={MINE_DENIED} />)
    expect(screen.getByText('Denied by Marcus Bell')).toBeInTheDocument()
    expect(screen.getByText('Marcus Bell’s note')).toBeInTheDocument()
    expect(
      screen.getByText(
        '“We’re short-staffed for the back-to-school sale that week. Could you pick another Friday?”',
      ),
    ).toBeInTheDocument()
  })

  it('shows Canceled with no decider line', () => {
    inList(<RequestRow variant="mine" request={MINE_CANCELED} />)
    expect(screen.getByText('Canceled')).toBeInTheDocument()
  })

  it('tints on hover and while anything inside has focus, in a three-column grid', () => {
    inList(
      <RequestRow
        variant="mine"
        request={MINE_APPROVED}
        canCancel
        onCancel={vi.fn<() => void>()}
      />,
    )
    const row = screen.getByRole('listitem')
    expect(row.className).toContain('hover:bg-surface-sunken')
    expect(row.className).toContain('focus-within:bg-surface-sunken')
    expect(row.className).toContain('grid-cols-[minmax(0,1fr)_minmax(0,240px)_96px]')
    expect(row.className).toContain('max-sm:grid-cols-[minmax(0,1fr)_auto]')
  })
})

describe('RequestRow, team', () => {
  it('shows a 32 px avatar with the name, and no Cancel', () => {
    inList(<RequestRow variant="team" request={TEAM_APPROVED} decidedLine="Approved October 5" />)
    const row = screen.getByRole('listitem')
    expect(within(row).getByText('Vikram Morales')).toBeInTheDocument()
    expect(row.querySelector('[data-slot="avatar"]')).toHaveAttribute('data-size', 'row')
    expect(within(row).getByText('VM')).toBeInTheDocument()
    expect(within(row).getByText('Approved October 5')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('labels the note Your note', () => {
    inList(
      <RequestRow
        variant="team"
        request={{ ...TEAM_APPROVED, status: 'denied', decisionNote: 'Not that week.' }}
        decidedLine="Denied today"
        noteLabel="Your note"
      />,
    )
    expect(screen.getByText('Your note')).toBeInTheDocument()
    expect(screen.getByText('“Not that week.”')).toBeInTheDocument()
  })

  it('shows a recorded sick request with no decision line', () => {
    inList(<RequestRow variant="team" request={TEAM_SICK} />)
    expect(screen.getByText('Sick time · 3 hours')).toBeInTheDocument()
    expect(screen.getByText('Recorded')).toBeInTheDocument()
  })

  it('uses the person grid and stacks on a phone', () => {
    inList(<RequestRow variant="team" request={TEAM_SICK} />)
    const row = screen.getByRole('listitem')
    expect(row.className).toContain('grid-cols-[minmax(0,220px)_minmax(0,1fr)_minmax(0,220px)]')
    expect(row.className).toContain('max-sm:grid-cols-[minmax(0,1fr)]')
  })
})

describe('RequestGroup', () => {
  it('has a small title and its rows in a list', () => {
    render(
      <RequestGroup title="Upcoming" empty="No upcoming time off.">
        <RequestRow variant="mine" request={MINE_APPROVED} />
      </RequestGroup>,
    )
    expect(screen.getByRole('heading', { level: 3, name: 'Upcoming' })).toBeInTheDocument()
    expect(screen.getByRole('list')).toContainElement(screen.getByRole('listitem'))
    expect(screen.queryByText('No upcoming time off.')).not.toBeInTheDocument()
  })

  it('shows the empty line when there are no rows', () => {
    render(<RequestGroup title="Upcoming" empty="No upcoming time off." />)
    expect(screen.getByText('No upcoming time off.')).toBeInTheDocument()
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument()
  })

  it('shows the empty line when the children are an empty list or false', () => {
    render(
      <RequestGroup title="Upcoming" empty="No upcoming time off.">
        {[[], false]}
      </RequestGroup>,
    )
    expect(screen.getByText('No upcoming time off.')).toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })
})
