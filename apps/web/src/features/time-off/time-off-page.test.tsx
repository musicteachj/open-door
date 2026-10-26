import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { installFakeApi } from '@/test/fake-api'
import { gate, installFakeTimeOff, type FakeTimeOffOptions } from '@/test/fake-time-off'
import { stubMediaQuery } from '@/test/media-query'
import { server } from '@/test/msw'
import { renderApp } from '@/test/render-app'
import { meFor } from '@/test/fixtures'
import { pageCopy } from '@/components/timeoff/labels'
import { useShellToast } from '@/features/shell/toast-store'
import {
  MINE_APPROVED,
  MINE_CANCELED,
  MINE_DENIED,
  MINE_RECORDED,
  MINE_WAITING,
} from '@/app/gallery/fixtures/timeoff'

afterEach(() => {
  vi.unstubAllGlobals()
})

async function openPage(options: FakeTimeOffOptions = {}) {
  installFakeApi('priya')
  const fake = installFakeTimeOff(options)
  const app = renderApp({ at: '/time-off' })
  await screen.findByRole('heading', { level: 3, name: 'Upcoming' })
  return { ...app, fake }
}

const toast = () => document.querySelector<HTMLElement>('[data-slot="toast"]')
const group = (title: string) =>
  screen
    .getByRole('heading', { level: 3, name: title })
    .closest<HTMLElement>('[data-slot="request-group"]')!
const rowsIn = (title: string) => within(group(title)).queryAllByRole('listitem')
const rowDates = (title: string) =>
  rowsIn(title).map((row) => row.querySelector('.font-semibold')!.textContent)
const requestButton = () =>
  screen.getByRole('button', { name: 'Request time off', expanded: false })
const myRequests = () => screen.getByRole('heading', { level: 2, name: 'My requests' })

describe('Time off: the page', () => {
  it('has the header with the sandbox pill, the balance cards, the schedule line, and the button', async () => {
    await openPage()
    const main = screen.getByRole('main')
    const title = within(main).getByRole('heading', { level: 1, name: 'Time off' })
    expect(title.closest('header')!.textContent).toMatch(/Sandbox resets in/)

    const pto = within(main).getByRole('region', { name: 'PTO available' })
    expect(within(pto).getByText('92 hours')).toBeVisible()
    expect(within(pto).getByText('11.5 days')).toBeVisible()
    expect(
      within(pto).getByRole('link', { name: 'Source: Handbook §4.1, Paid time off' }),
    ).toHaveAttribute('href', '/handbook/4.1')
    const sick = within(main).getByRole('region', { name: 'Sick leave available this year' })
    expect(within(sick).getByText('32 hours')).toBeVisible()
    expect(
      within(sick).getByRole('link', { name: 'Source: Handbook CA-4.3, Sick leave' }),
    ).toBeInTheDocument()

    expect(
      within(main).getByText(/^Your schedule: Monday to Friday, 8 hours a day/),
    ).toBeInTheDocument()
    expect(within(main).getByRole('link', { name: 'Handbook §3.1' })).toHaveAttribute(
      'href',
      '/handbook/3.1',
    )
    const button = requestButton()
    expect(button).toHaveAttribute('aria-expanded', 'false')
  })

  it('is in the nav as the current page', async () => {
    await openPage()
    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).getByRole('link', { name: 'Time off' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  it('lists Upcoming soonest first and Past newest first', async () => {
    await openPage({
      mine: [MINE_DENIED, MINE_APPROVED, MINE_CANCELED, MINE_RECORDED, MINE_WAITING],
    })
    expect(rowDates('Upcoming')).toEqual([
      'Thursday, October 22',
      'Friday, October 30',
      'Wednesday, December 23',
    ])
    expect(rowDates('Past')).toEqual(['Monday, October 12', 'Friday, August 28'])
  })

  it('puts a canceled or denied request in Past even when its days are ahead', async () => {
    const futureCanceled = { ...MINE_CANCELED, startDate: '2026-12-01', endDate: '2026-12-01' }
    await openPage({ mine: [futureCanceled] })
    expect(rowsIn('Upcoming')).toHaveLength(0)
    expect(screen.getByText('No upcoming time off.')).toBeInTheDocument()
    expect(rowDates('Past')).toEqual(['Tuesday, December 1'])
  })

  it('offers Cancel only where the request can be canceled, named for it', async () => {
    await openPage()
    expect(
      screen.getByRole('button', { name: 'Cancel PTO on Wednesday, December 23' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Cancel sick time on Thursday, October 22' }),
    ).toBeInTheDocument()
    // No Cancel in Past.
    expect(within(group('Past')).queryByRole('button')).not.toBeInTheDocument()
  })

  it('shows who decided, and a denial with its note', async () => {
    await openPage()
    expect(within(group('Upcoming')).getByText('Approved by Marcus Bell')).toBeInTheDocument()
    const denied = within(group('Past'))
      .getByText('Denied by Marcus Bell')
      .closest('li') as HTMLElement
    expect(within(denied).getByText('Marcus Bell’s note')).toBeInTheDocument()
    expect(within(denied).getByText(/short-staffed/)).toBeInTheDocument()
  })

  it('shows the empty lines when there are no requests', async () => {
    await openPage({ mine: [] })
    expect(screen.getByText('No upcoming time off.')).toBeInTheDocument()
    expect(screen.getByText('No past time off.')).toBeInTheDocument()
  })

  it('shows the API’s sick years: next year’s card is named for its year', async () => {
    installFakeApi('priya')
    installFakeTimeOff({
      balances: {
        sick: [
          {
            year: 2026,
            grantedMinutes: 2400,
            grantedLabel: '40 hours (5 days)',
            usedMinutes: 480,
            usedLabel: '8 hours (1 day)',
            bookedMinutes: 0,
            bookedLabel: '0 hours',
            availableMinutes: 1920,
            availableLabel: '32 hours (4 days)',
          },
          {
            year: 2027,
            grantedMinutes: 2400,
            grantedLabel: '40 hours (5 days)',
            usedMinutes: 0,
            usedLabel: '0 hours',
            bookedMinutes: 480,
            bookedLabel: '8 hours (1 day)',
            availableMinutes: 1920,
            availableLabel: '32 hours (4 days)',
          },
        ],
      },
    })
    renderApp({ at: '/time-off' })
    expect(
      await screen.findByRole('region', { name: 'Sick leave available this year' }),
    ).toBeVisible()
    expect(screen.getByRole('region', { name: 'Sick leave available in 2027' })).toBeVisible()
  })

  it('shows Cancel from the API’s canCancel, not from the dates', async () => {
    const closedByServer = { ...MINE_APPROVED, canCancel: false }
    await openPage({ mine: [closedByServer, MINE_WAITING] })
    expect(
      screen.queryByRole('button', { name: 'Cancel PTO on Wednesday, December 23' }),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel PTO on Friday, October 30' })).toBeVisible()
  })

  it('offers Cancel on a pending request whose days have passed, wherever it is listed', async () => {
    const lapsed = { ...MINE_WAITING, id: 'lapsed', startDate: '2026-10-09', endDate: '2026-10-09' }
    await openPage({ mine: [lapsed] })
    expect(rowsIn('Past')).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Cancel PTO on Friday, October 9' })).toBeVisible()
    // Nothing else in Past offers a button.
    expect(within(group('Past')).getAllByRole('button')).toHaveLength(1)
  })

  it('shows a request for December of next year in Upcoming, and asks up to the end of that year', async () => {
    const far = { ...MINE_WAITING, id: 'far', startDate: '2027-12-15', endDate: '2027-12-15' }
    const { fake } = await openPage({ mine: [far] })
    expect(rowDates('Upcoming')).toEqual(['Wednesday, December 15'])
    expect(fake.calls.requests.find((call) => call.scope === 'mine')!.to).toBe('2027-12-31')
  })

  it('writes the separator with the text before it, so a wrapped line never starts with it', async () => {
    await openPage()
    const line = screen.getByText(/^Your schedule:/)
    expect(line.textContent).toBe('Your schedule: Monday to Friday, 8 hours a day\u00a0·')
    // A plain space, then the link, in the same run of text.
    expect(line.nextSibling?.textContent).toBe(' ')
    expect(line.nextElementSibling).toBe(screen.getByRole('link', { name: 'Handbook §3.1' }))
  })

  it('leaves the calendar’s start to the API, which knows how far back sick time reaches', async () => {
    const { fake } = await openPage({ calendar: { sickLookbackDays: 90 } })
    expect(fake.calls.calendarWindows).toEqual([{ from: null, to: '2027-12-31' }])
  })

  it('reads the requests over a window wide enough for Past, from the API’s today', async () => {
    const { fake } = await openPage()
    const call = fake.calls.requests.find((item) => item.scope === 'mine')!
    expect(call.from! < '2026-10-20').toBe(true)
    expect(call.to! > '2026-10-20').toBe(true)
  })
})

describe('Time off: a read that fails after the page was shown', () => {
  it('keeps the page and the open form, since only a first load goes to the error page', async () => {
    const { user, queryClient } = await openPage()
    await user.click(requestButton())
    await screen.findByRole('region', { name: 'Request time off' })
    const boom = () =>
      HttpResponse.json(
        { type: 'about:blank', title: 'Boom', status: 500, instance: '/x' },
        { status: 500 },
      )
    server.use(
      http.get(`${window.location.origin}/api/v1/time-off/requests`, boom),
      http.get(`${window.location.origin}/api/v1/time-off/balances`, boom),
      http.get(`${window.location.origin}/api/v1/time-off/calendar`, boom),
    )
    await act(async () => {
      await queryClient.invalidateQueries()
    })
    await waitFor(() => expect(queryClient.isFetching()).toBe(0))
    expect(screen.queryByRole('heading', { name: 'Something went wrong on our side.' })).toBeNull()
    expect(screen.getByRole('region', { name: 'Request time off' })).toBeVisible()
    expect(myRequests()).toBeVisible()
  })
})

describe('Time off: loading and failing', () => {
  it('shows skeletons and says what is loading, then the page', async () => {
    installFakeApi('priya')
    const held = gate()
    installFakeTimeOff()
    server.use(
      http.get(`${window.location.origin}/api/v1/time-off/balances`, async () => {
        await held.promise
        return HttpResponse.json({
          personId: 'p',
          today: '2026-10-20',
          pto: (await import('@/app/gallery/fixtures/timeoff')).PTO_BALANCE,
          sick: [],
          rules: [],
        })
      }),
    )
    renderApp({ at: '/time-off' })
    await screen.findByRole('heading', { level: 1, name: 'Time off' })
    const status = document.querySelector('[data-slot="loading-status"]')!
    await waitFor(() => expect(status).toHaveTextContent('Loading your time off'))
    expect(
      document.querySelector('[data-slot="balance-card"][data-state="loading"]'),
    ).not.toBeNull()
    expect(screen.queryByRole('button', { name: 'Request time off' })).not.toBeInTheDocument()
    held.open()
    await screen.findByRole('heading', { level: 3, name: 'Upcoming' })
    expect(status).toHaveTextContent('')
  })

  it('lets a failed first load reach the global error page, with Retry', async () => {
    installFakeApi('priya')
    installFakeTimeOff()
    let failing = true
    server.use(
      http.get(`${window.location.origin}/api/v1/time-off/balances`, () =>
        failing
          ? HttpResponse.json(
              { type: 'about:blank', title: 'Boom', status: 500, instance: '/x' },
              { status: 500, headers: { 'X-Request-ID': 'c'.repeat(32) } },
            )
          : undefined,
      ),
    )
    const { user } = renderApp({ at: '/time-off' })
    expect(
      await screen.findByRole('heading', { name: 'Something went wrong on our side.' }),
    ).toBeVisible()
    // The shell stays around it.
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeVisible()
    failing = false
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('heading', { level: 3, name: 'Upcoming' })).toBeVisible()
  })
})

describe('Time off: canceling a request', () => {
  const cancelButton = () =>
    screen.getByRole('button', { name: 'Cancel PTO on Wednesday, December 23' })

  it('asks first, with focus on Keep it, and Keep it puts focus back on the row’s Cancel', async () => {
    const { user, fake } = await openPage()
    await user.click(cancelButton())
    const dialog = await screen.findByRole('alertdialog', {
      name: 'Cancel your time off on Wednesday, December 23?',
    })
    expect(within(dialog).getByText('8 hours go back to your balance.')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Keep it' })).toHaveFocus()

    await user.click(within(dialog).getByRole('button', { name: 'Keep it' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(cancelButton()).toHaveFocus()
    expect(fake.calls.cancels).toEqual([])
  })

  it('puts focus back on the row’s Cancel after Escape', async () => {
    const { user } = await openPage()
    await user.click(cancelButton())
    await screen.findByRole('alertdialog')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(cancelButton()).toHaveFocus()
  })

  it('cancels, says how many hours went back, and moves focus to "My requests"', async () => {
    const { user, fake } = await openPage()
    await user.click(cancelButton())
    await user.click(await screen.findByRole('button', { name: 'Cancel request' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(fake.calls.cancels).toEqual([MINE_APPROVED.id])
    await waitFor(() =>
      expect(toast()).toHaveTextContent('Canceled. 8 hours went back to your balance.'),
    )
    expect(myRequests()).toHaveFocus()
    expect(myRequests()).toHaveAttribute('tabindex', '-1')
    // The row moved to Past, where it reads Canceled and has no button.
    expect(rowDates('Upcoming')).not.toContain('Wednesday, December 23')
    expect(rowDates('Past')).toContain('Wednesday, December 23')
  })

  it('sends one cancel for two clicks that land before the page draws again, and thanks once', async () => {
    const { user, fake } = await openPage()
    await user.click(cancelButton())
    const confirm = await screen.findByRole('button', { name: 'Cancel request' })
    fireEvent.click(confirm)
    fireEvent.click(confirm)
    await waitFor(() => expect(toast()).toHaveTextContent('Canceled.'))
    expect(fake.calls.cancels).toHaveLength(1)
  })

  it('shows Canceling… while it runs, and sends one request however often it is pressed', async () => {
    const { user, fake } = await openPage()
    const held = gate()
    fake.state.holdCancel = held.promise
    await user.click(cancelButton())
    const confirm = await screen.findByRole('button', { name: 'Cancel request' })
    await user.click(confirm)
    const busy = await screen.findByRole('button', { name: 'Canceling…' })
    expect(busy).toHaveAttribute('aria-busy', 'true')
    await user.click(busy)
    held.open()
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(fake.calls.cancels).toHaveLength(1)
  })

  it('shows a calm refusal for a 409, refreshes the list, and still moves focus to the heading', async () => {
    const { user, fake } = await openPage()
    fake.state.cancelFailure = {
      status: 409,
      type: 'already-started',
      detail: 'This request has already started, so it can’t be canceled.',
    }
    await user.click(cancelButton())
    await user.click(await screen.findByRole('button', { name: 'Cancel request' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    await waitFor(() =>
      expect(toast()).toHaveTextContent(
        'This request has already started, so it can’t be canceled.',
      ),
    )
    expect(myRequests()).toHaveFocus()
    // The requests were read again.
    expect(fake.calls.requests.filter((item) => item.scope === 'mine').length).toBeGreaterThan(1)
  })

  it('keeps the dialog open after a server error, so the person can press Cancel request again', async () => {
    const { user, fake } = await openPage()
    fake.state.cancelFailure = { status: 500, type: 'about:blank', detail: 'Boom' }
    await user.click(cancelButton())
    await user.click(await screen.findByRole('button', { name: 'Cancel request' }))
    await waitFor(() => expect(toast()).toHaveTextContent(pageCopy.cancelFailed))
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()

    fake.state.cancelFailure = null
    await user.click(await screen.findByRole('button', { name: 'Cancel request' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(fake.calls.cancels).toHaveLength(2)
    await waitFor(() => expect(toast()).toHaveTextContent('Canceled.'))
  })

  it('keeps the toast for the person who canceled', async () => {
    const { user } = await openPage()
    await user.click(cancelButton())
    await user.click(await screen.findByRole('button', { name: 'Cancel request' }))
    await waitFor(() => expect(toast()).not.toBeNull())
    expect(useShellToast.getState().personId).toBe(meFor('priya').id)
  })
})

describe('Time off: the request form', () => {
  it('opens as a docked panel with focus on its title, and the page stays usable beside it', async () => {
    const { user } = await openPage()
    const button = requestButton()
    await user.click(button)
    const panel = await screen.findByRole('region', { name: 'Request time off' })
    expect(panel).toHaveClass('w-panel')
    expect(screen.getByRole('heading', { level: 2, name: 'Request time off' })).toHaveFocus()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    const open = screen.getByRole('button', { name: 'Request time off', expanded: true })
    expect(open).toHaveAttribute('aria-controls', panel.id)
    expect(open).not.toHaveAttribute('inert')
    // The page is still there beside it.
    expect(myRequests()).toBeVisible()
  })

  it('returns focus to "Request time off" from Close and from Cancel', async () => {
    const { user } = await openPage()
    await user.click(requestButton())
    await screen.findByRole('region', { name: 'Request time off' })
    await user.click(screen.getByRole('button', { name: 'Close' }))
    await waitFor(() => expect(requestButton()).toHaveFocus())
    expect(screen.queryByRole('region', { name: 'Request time off' })).not.toBeInTheDocument()

    await user.click(requestButton())
    const panel = await screen.findByRole('region', { name: 'Request time off' })
    await user.click(within(panel).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(requestButton()).toHaveFocus())
  })

  async function bookOctober30(user: ReturnType<typeof renderApp>['user']) {
    await user.click(requestButton())
    const panel = await screen.findByRole('region', { name: 'Request time off' })
    await user.click(within(panel).getByRole('button', { name: /^Dates/ }))
    await user.click(within(panel).getByRole('button', { name: /^Friday, October 30(,|$)/ }))
    await user.click(within(panel).getByRole('button', { name: 'Done' }))
    const submit = within(panel).getByRole('button', { name: 'Request time off' })
    await waitFor(() => expect(submit).toBeEnabled())
    return { panel, submit }
  }

  it('sends the request, closes the form, thanks with the approver’s name, and returns focus', async () => {
    const { user, fake } = await openPage()
    const { submit } = await bookOctober30(user)
    await user.click(submit)
    await waitFor(() =>
      expect(screen.queryByRole('region', { name: 'Request time off' })).toBeNull(),
    )
    expect(fake.calls.creates).toEqual([
      { type: 'pto', startDate: '2026-10-30', endDate: '2026-10-30', partialMinutes: null },
    ])
    await waitFor(() => expect(toast()).toHaveTextContent('Requested. Marcus Bell will review it.'))
    expect(requestButton()).toHaveFocus()
    // The new request is in Upcoming, waiting for approval.
    await waitFor(() => expect(rowDates('Upcoming')).toContain('Friday, October 30'))
  })

  it('says "Recorded." for sick time', async () => {
    const { user } = await openPage()
    await user.click(requestButton())
    const panel = await screen.findByRole('region', { name: 'Request time off' })
    await user.click(within(panel).getByRole('radio', { name: 'Sick time' }))
    await user.click(within(panel).getByRole('button', { name: /^Dates/ }))
    await user.click(within(panel).getByRole('button', { name: /^Wednesday, October 21(,|$)/ }))
    await user.click(within(panel).getByRole('button', { name: 'Done' }))
    const submit = within(panel).getByRole('button', { name: 'Record sick time' })
    await waitFor(() => expect(submit).toBeEnabled())
    await user.click(submit)
    await waitFor(() => expect(toast()).toHaveTextContent('Recorded.'))
    expect(requestButton()).toHaveFocus()
  })

  it('starts clean each time it opens', async () => {
    const { user } = await openPage()
    await bookOctober30(user)
    await user.click(screen.getByRole('button', { name: 'Close' }))
    await waitFor(() => expect(requestButton()).toHaveFocus())
    await user.click(requestButton())
    await screen.findByText('Pick dates to see what this uses.')
  })

  it('is a modal bottom sheet on a narrow window, and returns focus the same way', async () => {
    stubMediaQuery(true)
    const { user } = await openPage()
    await user.click(requestButton())
    const dialog = await screen.findByRole('dialog', { name: 'Request time off' })
    expect(within(dialog).getByRole('heading', { name: 'Request time off' })).toHaveFocus()
    expect(screen.queryByRole('region', { name: 'Request time off' })).not.toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Close' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(requestButton()).toHaveFocus())
  })

  it('names the manager in the form’s footer, from the summary', async () => {
    const { user } = await openPage()
    await user.click(requestButton())
    const panel = await screen.findByRole('region', { name: 'Request time off' })
    await waitFor(() =>
      expect(
        within(panel).getByText('Marcus Bell, your manager, reviews PTO requests.'),
      ).toBeVisible(),
    )
  })
})
