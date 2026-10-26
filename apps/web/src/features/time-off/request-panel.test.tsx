import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import type { CalendarOut, CheckOut, RequestOut } from '@/api/generated'
import {
  CHECK_HOLIDAY,
  CHECK_NOT_ENOUGH,
  CHECK_ONE_DAY,
  CHECK_SICK_HOURS,
  CHECK_WEEKEND,
  TODAY,
} from '@/app/gallery/fixtures/timeoff'
import { createQueryClient } from '@/lib/query-client'
import { stubAbsoluteUrls } from '@/test/absolute-urls'
import { gate, installFakeTimeOff } from '@/test/fake-time-off'
import { RequestPanel } from './request-panel'

const CALENDAR: CalendarOut = {
  scheduledWeekdays: [1, 2, 3, 4, 5],
  dayMinutes: 480,
  dayLabel: '8 hours',
  holidays: [{ day: '2026-11-26', name: 'Thanksgiving' }],
  earliestStart: { pto: TODAY, sick: '2026-09-20' },
  latestEnd: '2027-12-31',
  sickLookbackDays: 30,
  halfDayMinutes: 240,
}

function setup({
  docked = true,
  calendar = {},
}: { docked?: boolean; calendar?: Partial<CalendarOut> } = {}) {
  const onClose = vi.fn<() => void>()
  const onSubmitted = vi.fn<(request: RequestOut) => void>()
  stubAbsoluteUrls()
  const fake = installFakeTimeOff()
  const queryClient = createQueryClient({ onUnauthorized: vi.fn<() => void>(), retryDelayMs: 0 })
  const user = userEvent.setup()
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <RequestPanel
          docked={docked}
          id="request-form"
          today={TODAY}
          calendar={{ ...CALENDAR, ...calendar }}
          approverName="Marcus Bell"
          onClose={onClose}
          onSubmitted={onSubmitted}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { fake, user, onClose, onSubmitted, queryClient }
}

const day = (name: string) => screen.getByRole('button', { name: new RegExp(`^${name}(,|$)`) })
const submit = () => screen.getByRole('button', { name: /^Request time off$|^Record sick time$/ })

type User = ReturnType<typeof userEvent.setup>

/** Opens the picker, picks the days (one for a single day), and closes the picker. */
async function pick(user: User, first: string, last?: string) {
  const field = screen.getByRole('button', { name: /^Dates/ })
  if (field.getAttribute('aria-expanded') !== 'true') await user.click(field)
  await user.click(day(first))
  if (last) await user.click(day(last))
  await user.click(screen.getByRole('button', { name: 'Done' }))
}

const preview = () => document.querySelector('[data-slot="preview-live"]') as HTMLElement

describe('RequestPanel', () => {
  it('opens with focus on its title and nothing to check yet', async () => {
    const { fake } = setup()
    expect(screen.getByRole('heading', { level: 2, name: 'Request time off' })).toHaveFocus()
    expect(screen.getByText('Pick dates to see what this uses.')).toBeInTheDocument()
    expect(submit()).toBeDisabled()
    expect(fake.calls.checks).toEqual([])
  })

  it('asks the server to check the picked day, and shows its answer', async () => {
    const { fake, user } = setup()
    await pick(user, 'Friday, October 30')
    await waitFor(() => expect(submit()).toBeEnabled())
    expect(fake.calls.checks).toEqual([
      { type: 'pto', startDate: '2026-10-30', endDate: '2026-10-30', partialMinutes: null },
    ])
    expect(within(preview()).getByText('Friday, October 30')).toBeInTheDocument()
    expect(
      within(preview()).getByText(/84 hours \(10\.5 days\) left after this/),
    ).toBeInTheDocument()
  })

  it('checks again on each change: the type, the dates, and how much', async () => {
    const { fake, user } = setup()
    await pick(user, 'Friday, October 30')
    await waitFor(() => expect(submit()).toBeEnabled())
    await user.click(screen.getByRole('radio', { name: 'Half day (4 hours)' }))
    await waitFor(() => expect(fake.calls.checks).toHaveLength(2))
    expect(fake.calls.checks[1]).toMatchObject({ partialMinutes: 240 })
    await user.click(screen.getByRole('radio', { name: 'Sick time' }))
    await waitFor(() => expect(fake.calls.checks).toHaveLength(3))
    // A half day isn't offered for sick time, so the type's change goes back to a full day.
    expect(fake.calls.checks[2]).toEqual({
      type: 'sick',
      startDate: '2026-10-30',
      endDate: '2026-10-30',
      partialMinutes: null,
    })
  })

  it('holds Submit and mutes the old figures from the change until its check arrives', async () => {
    const { fake, user } = setup()
    await pick(user, 'Friday, October 30')
    await waitFor(() => expect(submit()).toBeEnabled())

    const held = gate()
    fake.state.check = async () => {
      await held.promise
      return CHECK_NOT_ENOUGH
    }
    await user.click(screen.getByRole('radio', { name: 'Half day (4 hours)' }))
    // The old answer is still on screen, muted, and nothing can be sent beside it.
    expect(submit()).toBeDisabled()
    expect(preview()).toHaveAttribute('aria-busy', 'true')
    expect(within(preview()).getByText('Friday, October 30')).toBeInTheDocument()

    held.open()
    await waitFor(() => expect(preview()).not.toHaveAttribute('aria-busy', 'true'))
    expect(screen.getByRole('alert')).toHaveTextContent('This request needs')
    expect(submit()).toBeDisabled()
  })

  it('drops an answer that arrives for older inputs, and keeps waiting for the current one', async () => {
    const { fake, user } = setup()
    const first = gate()
    const second = gate()
    const answers = new Map<string, { gate: ReturnType<typeof gate>; check: CheckOut }>([
      ['2026-10-30', { gate: first, check: CHECK_ONE_DAY }],
      ['2026-10-28', { gate: second, check: CHECK_WEEKEND }],
    ])
    fake.state.check = async (body) => {
      const held = answers.get(body.startDate)!
      await held.gate.promise
      return held.check
    }

    await pick(user, 'Friday, October 30')
    await waitFor(() => expect(fake.calls.checks).toHaveLength(1))
    await pick(user, 'Wednesday, October 28')
    await waitFor(() => expect(fake.calls.checks).toHaveLength(2))

    // The check for the first day answers last of all, after the second day's own.
    expect(submit()).toBeDisabled()
    second.open()
    await waitFor(() => expect(submit()).toBeEnabled())
    expect(
      within(preview()).getByText(/76 hours \(9\.5 days\) left after this/),
    ).toBeInTheDocument()
    first.open()
    // Let the late answer land: it must change nothing.
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(within(preview()).queryByText(/84 hours/)).not.toBeInTheDocument()
    expect(
      within(preview()).getByText(/76 hours \(9\.5 days\) left after this/),
    ).toBeInTheDocument()
    expect(submit()).toBeEnabled()
  })

  it('keeps Submit off while the answer for the new inputs is still on its way, whatever the old one said', async () => {
    const { fake, user } = setup()
    const held = gate()
    fake.state.check = async () => {
      await held.promise
      return CHECK_ONE_DAY
    }
    await pick(user, 'Friday, October 30')
    await waitFor(() => expect(fake.calls.checks).toHaveLength(1))
    expect(submit()).toBeDisabled()
    held.open()
    await waitFor(() => expect(submit()).toBeEnabled())
  })

  it('sends exactly what the form reports: a half day, as 240 minutes', async () => {
    const { fake, user, onSubmitted } = setup()
    await pick(user, 'Friday, October 30')
    await user.click(screen.getByRole('radio', { name: 'Half day (4 hours)' }))
    await waitFor(() => expect(submit()).toBeEnabled())
    await user.click(submit())
    await waitFor(() => expect(onSubmitted).toHaveBeenCalled())
    expect(fake.calls.creates).toEqual([
      { type: 'pto', startDate: '2026-10-30', endDate: '2026-10-30', partialMinutes: 240 },
    ])
  })

  it('sends a full day with no partial amount for a range, even after a half day was chosen', async () => {
    const { fake, user, onSubmitted } = setup()
    await pick(user, 'Friday, October 30')
    await user.click(screen.getByRole('radio', { name: 'Half day (4 hours)' }))
    await pick(user, 'Wednesday, October 28', 'Friday, October 30')
    await waitFor(() => expect(submit()).toBeEnabled())
    await user.click(submit())
    await waitFor(() => expect(onSubmitted).toHaveBeenCalled())
    expect(fake.calls.creates).toEqual([
      { type: 'pto', startDate: '2026-10-28', endDate: '2026-10-30', partialMinutes: null },
    ])
  })

  it('sends sick hours as minutes for one day', async () => {
    const { fake, user, onSubmitted } = setup()
    fake.state.check = () => CHECK_SICK_HOURS
    await user.click(screen.getByRole('radio', { name: 'Sick time' }))
    await pick(user, 'Thursday, October 22')
    await user.click(screen.getByRole('radio', { name: 'Some hours' }))
    await waitFor(() => expect(submit()).toBeEnabled())
    await user.click(submit())
    await waitFor(() => expect(onSubmitted).toHaveBeenCalled())
    expect(fake.calls.creates).toEqual([
      { type: 'sick', startDate: '2026-10-22', endDate: '2026-10-22', partialMinutes: 180 },
    ])
  })

  it('shows Requesting… while the send is on its way, then reports the new request', async () => {
    const { fake, user, onSubmitted } = setup()
    const held = gate()
    fake.state.holdCreate = held.promise
    await pick(user, 'Friday, October 30')
    await waitFor(() => expect(submit()).toBeEnabled())
    await user.click(submit())
    const busy = await screen.findByRole('button', { name: 'Requesting…' })
    expect(busy).toHaveAttribute('aria-busy', 'true')
    expect(onSubmitted).not.toHaveBeenCalled()
    held.open()
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledTimes(1))
    expect(onSubmitted.mock.calls[0]![0]).toMatchObject({
      type: 'pto',
      startDate: '2026-10-30',
      status: 'pending',
    })
  })

  it("shows the server's refusal in the form, checks again, and stays open", async () => {
    const { fake, user, onSubmitted, onClose } = setup()
    await pick(user, 'Friday, October 30')
    await waitFor(() => expect(submit()).toBeEnabled())
    fake.state.createFailure = {
      status: 422,
      type: 'overlaps',
      detail: 'Some of those days are already covered by another request.',
    }
    fake.state.check = () => CHECK_HOLIDAY
    await user.click(submit())
    expect(
      await screen.findByText('Some of those days are already covered by another request.'),
    ).toBeVisible()
    expect(onSubmitted).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
    // The preview is read again so it shows what the server now says.
    await waitFor(() => expect(fake.calls.checks.length).toBeGreaterThan(1))
  })

  it('says to try again, and that nothing changed, when the send fails without an answer', async () => {
    const { fake, user, onSubmitted } = setup()
    await pick(user, 'Friday, October 30')
    await waitFor(() => expect(submit()).toBeEnabled())
    fake.state.createFailure = { status: 500, type: 'about:blank', detail: '' }
    await user.click(submit())
    expect(
      await screen.findByText(
        'Couldn’t send this request. Nothing was changed. Try again in a moment.',
      ),
    ).toBeVisible()
    expect(onSubmitted).not.toHaveBeenCalled()
    expect(submit()).toBeEnabled()
  })

  it('takes the refusal away when an input changes', async () => {
    const { fake, user } = setup()
    await pick(user, 'Friday, October 30')
    await waitFor(() => expect(submit()).toBeEnabled())
    fake.state.createFailure = { status: 500, type: 'about:blank', detail: '' }
    await user.click(submit())
    await screen.findByText(/Couldn’t send this request/)
    await user.click(screen.getByRole('radio', { name: 'Half day (4 hours)' }))
    expect(screen.queryByText(/Couldn’t send this request/)).not.toBeInTheDocument()
  })

  it('maps the calendar to the picker: PTO starts today and sick time reaches back 30 days', async () => {
    const { user } = setup()
    await user.click(screen.getByRole('button', { name: /^Dates/ }))
    expect(screen.getByText('Past days can’t be picked for PTO')).toBeInTheDocument()
    expect(day('Monday, October 19')).toHaveAttribute('aria-disabled', 'true')
    expect(day('Tuesday, October 20')).not.toHaveAttribute('aria-disabled')
    await user.click(screen.getByRole('radio', { name: 'Sick time' }))
    expect(screen.getByText('Sick time can go back 30 days, to September 20')).toBeInTheDocument()
    expect(day('Monday, October 19')).not.toHaveAttribute('aria-disabled')
  })

  it('writes the sick look-back from the calendar’s own number of days', async () => {
    const { user } = setup({
      calendar: { sickLookbackDays: 14, earliestStart: { pto: TODAY, sick: '2026-10-06' } },
    })
    await user.click(screen.getByRole('radio', { name: 'Sick time' }))
    await user.click(screen.getByRole('button', { name: /^Dates/ }))
    expect(screen.getByText('Sick time can go back 14 days, to October 6')).toBeInTheDocument()
  })

  it('sends the calendar’s half-day minutes, not a number of its own', async () => {
    const { fake, user, onSubmitted } = setup({ calendar: { halfDayMinutes: 300 } })
    await pick(user, 'Friday, October 30')
    await user.click(screen.getByRole('radio', { name: 'Half day (4 hours)' }))
    await waitFor(() => expect(fake.calls.checks).toHaveLength(2))
    expect(fake.calls.checks[1]).toMatchObject({ partialMinutes: 300 })
    await waitFor(() => expect(submit()).toBeEnabled())
    await user.click(submit())
    await waitFor(() => expect(onSubmitted).toHaveBeenCalled())
    expect(fake.calls.creates[0]).toMatchObject({ partialMinutes: 300 })
  })

  it('says the preview did not load when the check fails, and keeps Submit off', async () => {
    const { fake, user } = setup()
    fake.state.check = async () => {
      throw new Error('boom')
    }
    await pick(user, 'Friday, October 30')
    expect(await screen.findByText('The preview didn’t load.')).toBeVisible()
    expect(screen.getByRole('alert')).toHaveTextContent('The preview didn’t load.')
    expect(submit()).toBeDisabled()
  })

  it('asks again for the same days when Try again is pressed, and then shows the preview', async () => {
    const { fake, user } = setup()
    fake.state.check = async () => {
      throw new Error('boom')
    }
    await pick(user, 'Friday, October 30')
    const retry = await screen.findByRole('button', { name: 'Try again' })
    expect(fake.calls.checks).toHaveLength(1)

    fake.state.check = () => CHECK_ONE_DAY
    await user.click(retry)

    await waitFor(() => expect(fake.calls.checks).toHaveLength(2))
    expect(fake.calls.checks[1]).toEqual(fake.calls.checks[0])
    expect(await within(preview()).findByText('Friday, October 30')).toBeInTheDocument()
    expect(screen.queryByText('The preview didn’t load.')).not.toBeInTheDocument()
    expect(submit()).toBeEnabled()
  })

  it('keeps Submit off while Try again is waiting for its answer', async () => {
    const { fake, user } = setup()
    fake.state.check = async () => {
      throw new Error('boom')
    }
    await pick(user, 'Friday, October 30')
    const retry = await screen.findByRole('button', { name: 'Try again' })
    const held = gate()
    fake.state.check = async () => {
      await held.promise
      return CHECK_ONE_DAY
    }
    await user.click(retry)
    expect(submit()).toBeDisabled()
    held.open()
    await waitFor(() => expect(submit()).toBeEnabled())
  })

  it('takes the preview message away when the next check answers', async () => {
    const { fake, user } = setup()
    fake.state.check = async () => {
      throw new Error('boom')
    }
    await pick(user, 'Friday, October 30')
    await screen.findByText(/The preview didn’t load/)
    fake.state.check = () => CHECK_ONE_DAY
    await user.click(screen.getByRole('radio', { name: 'Half day (4 hours)' }))
    await waitFor(() => expect(submit()).toBeEnabled())
    expect(screen.queryByText(/The preview didn’t load/)).not.toBeInTheDocument()
  })

  it('closes from Close and Cancel', async () => {
    const { user, onClose } = setup()
    await user.click(screen.getByRole('button', { name: 'Close' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('is the modal bottom sheet when it is not docked', async () => {
    setup({ docked: false })
    expect(await screen.findByRole('dialog', { name: 'Request time off' })).toBeInTheDocument()
  })
})
