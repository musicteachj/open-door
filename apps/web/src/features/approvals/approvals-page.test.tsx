import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import {
  PRIYA_WAITING,
  TEAM_APPROVED,
  TEAM_DENIED,
  TEAM_SICK,
  ZARA_WAITING,
} from '@/app/gallery/fixtures/timeoff'
import { useShellToast } from '@/features/shell/toast-store'
import { installFakeApi } from '@/test/fake-api'
import { gate, installFakeTimeOff, type FakeTimeOffOptions } from '@/test/fake-time-off'
import { meFor } from '@/test/fixtures'
import { server } from '@/test/msw'
import { renderApp } from '@/test/render-app'

async function openPage(options: FakeTimeOffOptions = {}) {
  installFakeApi('marcus')
  const fake = installFakeTimeOff({ manager: true, ...options })
  const app = renderApp({ at: '/approvals' })
  await screen.findByRole('heading', { level: 2, name: /^Waiting for you/ })
  await screen.findByRole('heading', { level: 2, name: 'Recent decisions' })
  return { ...app, fake }
}

const toast = () => document.querySelector<HTMLElement>('[data-slot="toast"]')
const waitingHeading = () => screen.getByRole('heading', { level: 2, name: /^Waiting for you/ })
const section = (name: string) =>
  screen.getByRole('heading', { level: 2, name }).closest('section') as HTMLElement
const cards = () => [...document.querySelectorAll<HTMLElement>('[data-slot="approval-card"]')]
const cardNames = () => cards().map((card) => card.querySelector('h3')!.textContent)
const approve = (who: string, dates: string) =>
  screen.getByRole('button', { name: `Approve ${who}’s PTO, ${dates}` })
const deny = (who: string, dates: string) =>
  screen.getByRole('button', { name: `Deny ${who}’s PTO, ${dates}` })
// A third waiting request, sent last, so that Priya's is in the middle.
const TOMAS_WAITING = {
  ...PRIYA_WAITING,
  id: 'req-tomas-nov-2',
  person: { ...PRIYA_WAITING.person, id: 'person-tomas', name: 'Tomas Reyes' },
  startDate: '2026-11-02',
  endDate: '2026-11-02',
  createdAt: '2026-10-21T16:00:00Z',
}
const TOMAS = ['Tomas Reyes', 'November 2'] as const
const ZARA = ['Zara Bautista', 'November 9 to 10'] as const
const PRIYA = ['Priya Raman', 'October 30'] as const

describe('Approvals: who can see it', () => {
  it('shows the Not found page to someone who manages no one, and asks for nothing', async () => {
    installFakeApi('priya')
    const fake = installFakeTimeOff()
    renderApp({ at: '/approvals' })
    expect(
      await screen.findByRole('heading', { level: 1, name: "We couldn't find that page." }),
    ).toBeVisible()
    expect(fake.calls.requests.filter((call) => call.scope !== 'mine')).toEqual([])
    expect(screen.queryByRole('link', { name: /^Approvals/ })).not.toBeInTheDocument()
  })

  it('shows a manager the page, with Approvals current in the nav', async () => {
    await openPage()
    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).getByRole('link', { name: 'Approvals, 2 waiting' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })
})

describe('Approvals: the page', () => {
  it('has the header with the sandbox pill, and "Waiting for you" with its count and subtitle', async () => {
    await openPage()
    const title = screen.getByRole('heading', { level: 1, name: 'Approvals' })
    expect(title.closest('header')!.textContent).toMatch(/Sandbox resets in/)
    expect(waitingHeading()).toHaveAccessibleName('Waiting for you, 2')
    expect(waitingHeading()).toHaveAttribute('tabindex', '-1')
    expect(
      screen.getByText(
        'PTO requests from your direct reports, oldest first. Sick time is recorded, not approved, so it appears only under Coming up.',
      ),
    ).toBeInTheDocument()
  })

  it('lists the waiting requests oldest sent first, with their facts and coverage', async () => {
    await openPage({ waiting: [PRIYA_WAITING, ZARA_WAITING] })
    expect(cardNames()).toEqual(['Zara Bautista', 'Priya Raman'])
    const zara = cards()[0]!
    expect(within(zara).getByText('Sent October 17')).toBeInTheDocument()
    expect(within(zara).getByText('PTO · 16 hours (2 days)')).toBeInTheDocument()
    expect(within(zara).getByText('62 hours (7.75 days) available after this')).toBeInTheDocument()
    expect(
      within(zara).getByText('Also off: Vikram Morales, Tuesday, November 10 · PTO'),
    ).toBeInTheDocument()
    expect(
      within(cards()[1]!).getByText('No one else on your team is off that day.'),
    ).toBeInTheDocument()
  })

  it('names each Approve and Deny for its request', async () => {
    await openPage()
    expect(approve(...ZARA)).toBeVisible()
    expect(deny(...ZARA)).toBeVisible()
    expect(approve(...PRIYA)).toBeVisible()
  })

  it('never offers sick time as something to decide', async () => {
    const sickWaiting = { ...ZARA_WAITING, id: 'sick-one', type: 'sick' as const }
    await openPage({ waiting: [sickWaiting, PRIYA_WAITING] })
    expect(cardNames()).toEqual(['Priya Raman'])
  })

  it('shows what is coming up on the team, soonest first, without anything to press', async () => {
    await openPage()
    const coming = section('Coming up on your team')
    expect(
      within(coming).getByText(
        'Approved and recorded time off in the next 30 days, soonest first.',
      ),
    ).toBeInTheDocument()
    const rows = within(coming).getAllByRole('listitem')
    expect(rows.map((row) => within(row).getByText(/^(Malik|Vikram)/).textContent)).toEqual([
      'Malik Flores',
      'Vikram Morales',
    ])
    expect(within(coming).getByText('Sick time · 3 hours')).toBeInTheDocument()
    expect(within(coming).getByText('Recorded')).toBeInTheDocument()
    expect(within(coming).queryByRole('button')).not.toBeInTheDocument()
  })

  it('shows only the viewer’s own decisions, newest first, with "Your note" and the decision line', async () => {
    const someoneElses = {
      ...TEAM_APPROVED,
      id: 'other',
      decidedBy: { id: 'person-dana', name: 'Dana Whitfield' },
      decidedAt: '2026-10-19T17:00:00Z',
    }
    await openPage({ team: [TEAM_DENIED, someoneElses, TEAM_APPROVED, TEAM_SICK] })
    const recent = section('Recent decisions')
    expect(
      within(recent).getByText('Your decisions from the last 90 days, newest first.'),
    ).toBeInTheDocument()
    const rows = within(recent).getAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(within(rows[0]!).getByText('Vikram Morales')).toBeInTheDocument()
    expect(within(rows[0]!).getByText('Approved October 5')).toBeInTheDocument()
    expect(within(rows[1]!).getByText('Priya Raman')).toBeInTheDocument()
    expect(within(rows[1]!).getByText('Denied August 20')).toBeInTheDocument()
    expect(within(rows[1]!).getByText('Your note')).toBeInTheDocument()
    expect(within(rows[1]!).getByText(/short-staffed/)).toBeInTheDocument()
  })

  it('shows the empty lines for each list', async () => {
    await openPage({ waiting: [], team: [] })
    expect(
      screen.getByText(
        'Nothing is waiting for you. When someone on your team asks for time off, it shows up here.',
      ),
    ).toBeInTheDocument()
    expect(waitingHeading()).toHaveAccessibleName('Waiting for you')
    expect(screen.getByText('No time off on your team in the next 30 days.')).toBeInTheDocument()
    expect(screen.getByText('No decisions in the last 90 days.')).toBeInTheDocument()
  })

  it('asks for the team over the next 30 days, and for its own decisions over the last 90 days, from the API’s today', async () => {
    const { fake } = await openPage()
    const reads = fake.calls.requests.filter((call) => call.scope !== 'mine')
    expect(reads).toContainEqual({ scope: 'team', from: '2026-10-20', to: '2026-11-19' })
    expect(reads).toContainEqual({ scope: 'decided', from: '2026-07-22', to: '2026-10-20' })
    // The two lists no longer read the same requests: only Coming up asks for the team.
    expect(reads.filter((call) => call.scope === 'team')).toHaveLength(1)
  })
})

describe('Approvals: windows and sources', () => {
  it('reads today from the summary, not from the balances', async () => {
    const { fake } = await openPage()
    expect(fake.calls.balances).toBe(0)
    expect(fake.calls.summary).toBeGreaterThan(0)
  })

  it('shows a recent decision about leave in December of next year', async () => {
    const far = {
      ...TEAM_APPROVED,
      id: 'far',
      startDate: '2027-12-15',
      endDate: '2027-12-15',
      decidedAt: '2026-10-19T17:00:00Z',
    }
    await openPage({ team: [far] })
    const recent = within(section('Recent decisions')).getAllByRole('listitem')
    expect(within(recent[0]!).getByText('Wednesday, December 15')).toBeInTheDocument()
  })

  it('keeps the page when a read again fails after the data was shown', async () => {
    const { user } = await openPage()
    server.use(
      http.get(`${window.location.origin}/api/v1/time-off/requests`, () =>
        HttpResponse.json(
          { type: 'about:blank', title: 'Boom', status: 500, instance: '/x' },
          { status: 500 },
        ),
      ),
    )
    await user.click(approve(...PRIYA))
    await user.click(await screen.findByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(toast()).not.toBeNull())
    expect(screen.queryByRole('heading', { name: 'Something went wrong on our side.' })).toBeNull()
    expect(waitingHeading()).toBeVisible()
  })
})

describe('Approvals: loading and failing', () => {
  it('shows skeleton cards and says what is loading, then the page', async () => {
    installFakeApi('marcus')
    installFakeTimeOff({ manager: true })
    const held = gate()
    server.use(
      http.get(`${window.location.origin}/api/v1/time-off/requests`, async () => {
        await held.promise
        return HttpResponse.json({ items: [], fromDate: '2026-10-20', toDate: '2026-10-20' })
      }),
    )
    renderApp({ at: '/approvals' })
    await screen.findByRole('heading', { level: 1, name: 'Approvals' })
    const status = document.querySelector('[data-slot="loading-status"]')!
    await waitFor(() => expect(status).toHaveTextContent('Loading approvals'))
    expect(
      document.querySelectorAll('[data-slot="approval-card"][data-state="loading"]'),
    ).toHaveLength(2)
    held.open()
    await waitFor(() => expect(status).toHaveTextContent(''))
  })

  it('lets a failed first load reach the global error page, with Retry', async () => {
    installFakeApi('marcus')
    installFakeTimeOff({ manager: true })
    let failing = true
    server.use(
      http.get(`${window.location.origin}/api/v1/time-off/requests`, ({ request }) =>
        failing && new URL(request.url).searchParams.get('scope') === 'waiting'
          ? HttpResponse.json(
              { type: 'about:blank', title: 'Boom', status: 500, instance: '/x' },
              { status: 500, headers: { 'X-Request-ID': 'd'.repeat(32) } },
            )
          : undefined,
      ),
    )
    const { user } = renderApp({ at: '/approvals' })
    expect(
      await screen.findByRole('heading', { name: 'Something went wrong on our side.' }),
    ).toBeVisible()
    failing = false
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('heading', { level: 2, name: /^Waiting for you/ })).toBeVisible()
  })
})

describe('Approvals: the dialogs', () => {
  it('opens the approve dialog with focus on Go back, and Go back returns focus to the button', async () => {
    const { user, fake } = await openPage()
    const opener = approve(...ZARA)
    await user.click(opener)
    const dialog = await screen.findByRole('alertdialog', { name: 'Approve Zara Bautista’s PTO?' })
    expect(
      within(dialog).getByText(/Monday, November 9 to Tuesday, November 10, 16 hours/),
    ).toBeVisible()
    expect(within(dialog).getByRole('button', { name: 'Go back' })).toHaveFocus()
    await user.click(within(dialog).getByRole('button', { name: 'Go back' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(opener).toHaveFocus()
    expect(fake.calls.decisions).toEqual([])
  })

  it('goes back with Escape, returning focus to the button that opened it', async () => {
    const { user } = await openPage()
    const opener = deny(...PRIYA)
    await user.click(opener)
    await screen.findByRole('alertdialog')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(opener).toHaveFocus()
  })

  it('opens the deny dialog with focus in the note, which keeps what was typed until the page leaves', async () => {
    const { user } = await openPage()
    await user.click(deny(...ZARA))
    const note = await screen.findByRole('textbox', { name: 'Note to Zara (optional)' })
    expect(note).toHaveFocus()
    await user.type(note, 'Inventory runs that week.')
    expect(note).toHaveValue('Inventory runs that week.')
  })

  it('starts each denial with an empty note', async () => {
    const { user } = await openPage()
    await user.click(deny(...ZARA))
    await user.type(await screen.findByRole('textbox'), 'A note for Zara')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    await user.click(deny(...PRIYA))
    expect(await screen.findByRole('textbox')).toHaveValue('')
  })
})

describe('Approvals: deciding', () => {
  it('approves: shows Approving…, then the toast, the move to Recent decisions, the lower count, and focus on the next Approve', async () => {
    const { user, fake } = await openPage()
    const held = gate()
    fake.state.holdDecision = held.promise
    await user.click(approve(...ZARA))
    await user.click(await screen.findByRole('button', { name: 'Approve' }))
    const busy = await screen.findByRole('button', { name: 'Approving…' })
    expect(busy).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('button', { name: 'Go back' })).toBeDisabled()
    // Escape does nothing while it is deciding.
    await user.keyboard('{Escape}')
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()

    held.open()
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(fake.calls.decisions).toEqual([{ id: ZARA_WAITING.id, body: { decision: 'approve' } }])
    await waitFor(() =>
      expect(toast()).toHaveTextContent('Approved. Zara will see it on the Time off page.'),
    )
    expect(cardNames()).toEqual(['Priya Raman'])
    expect(waitingHeading()).toHaveAccessibleName('Waiting for you, 1')
    expect(approve(...PRIYA)).toHaveFocus()
    // Zara's request moved to the top of Recent decisions.
    const recent = within(section('Recent decisions')).getAllByRole('listitem')
    expect(within(recent[0]!).getByText('Zara Bautista')).toBeInTheDocument()
    expect(within(recent[0]!).getByText('Approved today')).toBeInTheDocument()
    // And the nav count dropped with it.
    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(await within(nav).findByRole('link', { name: 'Approvals, 1 waiting' })).toBeVisible()
  })

  it('denies with a note: the toast says the note will be seen, and the note is sent', async () => {
    const { user, fake } = await openPage()
    await user.click(deny(...ZARA))
    await user.type(await screen.findByRole('textbox'), 'Inventory runs that week.')
    await user.click(screen.getByRole('button', { name: 'Deny' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(fake.calls.decisions).toEqual([
      { id: ZARA_WAITING.id, body: { decision: 'deny', note: 'Inventory runs that week.' } },
    ])
    await waitFor(() =>
      expect(toast()).toHaveTextContent('Denied. Zara will see your note on the Time off page.'),
    )
    const recent = within(section('Recent decisions')).getAllByRole('listitem')
    expect(within(recent[0]!).getByText('Your note')).toBeInTheDocument()
    expect(within(recent[0]!).getByText('Denied today')).toBeInTheDocument()
    expect(approve(...PRIYA)).toHaveFocus()
  })

  it.each(['\u001c\u001d\u001e\u001f', '\u0085'])(
    'treats a note of only %j as no note, as the server does',
    async (blank) => {
      const { user, fake } = await openPage()
      await user.click(deny(...PRIYA))
      fireEvent.change(await screen.findByRole('textbox'), { target: { value: blank } })
      await user.click(screen.getByRole('button', { name: 'Deny' }))
      await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
      expect(fake.calls.decisions).toEqual([{ id: PRIYA_WAITING.id, body: { decision: 'deny' } }])
      await waitFor(() =>
        expect(toast()).toHaveTextContent('Denied. Priya will see it on the Time off page.'),
      )
    },
  )

  it('denies without a note: the toast says it, and no note is sent', async () => {
    const { user, fake } = await openPage()
    await user.click(deny(...PRIYA))
    await user.click(await screen.findByRole('button', { name: 'Deny' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(fake.calls.decisions).toEqual([{ id: PRIYA_WAITING.id, body: { decision: 'deny' } }])
    await waitFor(() =>
      expect(toast()).toHaveTextContent('Denied. Priya will see it on the Time off page.'),
    )
  })

  it('treats a note of only spaces as no note', async () => {
    const { user, fake } = await openPage()
    await user.click(deny(...PRIYA))
    await user.type(await screen.findByRole('textbox'), '   ')
    await user.click(screen.getByRole('button', { name: 'Deny' }))
    await waitFor(() => expect(fake.calls.decisions).toHaveLength(1))
    expect(fake.calls.decisions[0]!.body).toEqual({ decision: 'deny' })
  })

  it('moves focus to the heading when the last waiting request is decided', async () => {
    const { user } = await openPage({ waiting: [PRIYA_WAITING] })
    await user.click(approve(...PRIYA))
    await user.click(await screen.findByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    await waitFor(() => expect(waitingHeading()).toHaveFocus())
    expect(waitingHeading()).toHaveAccessibleName('Waiting for you')
    expect(
      screen.getByText(
        'Nothing is waiting for you. When someone on your team asks for time off, it shows up here.',
      ),
    ).toBeInTheDocument()
  })

  it('moves focus to the nearest remaining request when the last one in the list is decided', async () => {
    const { user } = await openPage()
    await user.click(approve(...PRIYA))
    await user.click(await screen.findByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    await waitFor(() => expect(approve(...ZARA)).toHaveFocus())
  })

  it('moves focus to the next request after one in the middle is approved, not to the first', async () => {
    const { user } = await openPage({ waiting: [ZARA_WAITING, PRIYA_WAITING, TOMAS_WAITING] })
    await user.click(approve(...PRIYA))
    await user.click(await screen.findByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    await waitFor(() => expect(approve(...TOMAS)).toHaveFocus())
  })

  it('sends one decision however often the button is pressed', async () => {
    const { user, fake } = await openPage()
    const held = gate()
    fake.state.holdDecision = held.promise
    await user.click(approve(...ZARA))
    const confirm = await screen.findByRole('button', { name: 'Approve' })
    await user.click(confirm)
    const busy = await screen.findByRole('button', { name: 'Approving…' })
    await user.click(busy)
    held.open()
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(fake.calls.decisions).toHaveLength(1)
  })

  it('keeps the toast for the manager who decided', async () => {
    const { user } = await openPage()
    await user.click(approve(...ZARA))
    await user.click(await screen.findByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(toast()).not.toBeNull())
    expect(useShellToast.getState().personId).toBe(meFor('marcus').id)
  })
})

describe('Approvals: a request that has moved on', () => {
  async function decideStale(
    open: Awaited<ReturnType<typeof openPage>>,
    { drop = true }: { drop?: boolean } = {},
  ) {
    const { user, fake } = open
    fake.state.decideFailure = {
      status: 409,
      type: 'status-changed',
      detail: 'This request has changed since the page was loaded, so refresh to see it.',
    }
    // Zara canceled it, so the server no longer lists it as waiting.
    if (drop) fake.dropWaiting(ZARA_WAITING.id)
    await user.click(approve(...ZARA))
    await user.click(await screen.findByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
  }

  it('closes the dialog and shows that card muted with the Canceled badge, no actions, and the refusal as an alert', async () => {
    const open = await openPage()
    await decideStale(open)
    const zara = cards().find((card) => card.textContent?.includes('Zara Bautista'))!
    expect(zara).toHaveAttribute('data-state', 'conflict')
    expect(within(zara).getByText('Canceled')).toBeInTheDocument()
    expect(within(zara).queryByText('Sent October 17')).not.toBeInTheDocument()
    expect(within(zara).queryByRole('button')).not.toBeInTheDocument()
    expect(within(zara).getByRole('alert')).toHaveTextContent('Zara canceled this request.')
  })

  it('keeps that card on the page after the refresh drops it from the waiting list', async () => {
    const open = await openPage()
    await decideStale(open)
    // The queue was read again, and no longer has Zara in it.
    await waitFor(() =>
      expect(
        open.fake.calls.requests.filter((call) => call.scope === 'waiting').length,
      ).toBeGreaterThan(1),
    )
    expect(cardNames()).toEqual(['Zara Bautista', 'Priya Raman'])
    // The count, and the cards that can be decided, are only what still waits.
    expect(waitingHeading()).toHaveAccessibleName('Waiting for you, 1')
    expect(screen.getAllByRole('button', { name: /^Approve / })).toHaveLength(1)
  })

  it('moves focus to the next request’s Approve', async () => {
    const open = await openPage()
    await decideStale(open)
    await waitFor(() => expect(approve(...PRIYA)).toHaveFocus())
  })

  it('moves focus to the next request after a middle one has moved on, not to the first', async () => {
    const open = await openPage({ waiting: [ZARA_WAITING, PRIYA_WAITING, TOMAS_WAITING] })
    const { user, fake } = open
    fake.state.decideFailure = {
      status: 409,
      type: 'status-changed',
      detail: 'This request has changed since the page was loaded, so refresh to see it.',
    }
    fake.dropWaiting(PRIYA_WAITING.id)
    await user.click(approve(...PRIYA))
    await user.click(await screen.findByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    await waitFor(() => expect(approve(...TOMAS)).toHaveFocus())
  })

  it('does not hold a card on a 409 that says the request is still pending', async () => {
    const { user, fake } = await openPage()
    fake.state.decideFailure = {
      status: 409,
      type: 'status-changed',
      detail: 'This request has changed since the page was loaded, so refresh to see it.',
      currentStatus: 'pending',
    }
    await user.click(approve(...ZARA))
    await user.click(await screen.findByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    await waitFor(() =>
      expect(toast()).toHaveTextContent('This request has changed since the page was loaded'),
    )
    const zara = cards().find((card) => card.textContent?.includes('Zara Bautista'))!
    expect(zara).not.toHaveAttribute('data-state', 'conflict')
    expect(approve(...ZARA)).toBeEnabled()
  })

  it('does not hold a card on a 409 that names no known status: a toast, and the buttons stay', async () => {
    const { user, fake } = await openPage()
    fake.state.decideFailure = {
      status: 409,
      type: 'status-changed',
      detail: 'This request has changed since the page was loaded, so refresh to see it.',
      currentStatus: null,
    }
    await user.click(approve(...ZARA))
    await user.click(await screen.findByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    await waitFor(() =>
      expect(toast()).toHaveTextContent('This request has changed since the page was loaded'),
    )
    // The queue was read again and still lists it, so it is an ordinary card with its buttons.
    await waitFor(() =>
      expect(fake.calls.requests.filter((call) => call.scope === 'waiting').length).toBeGreaterThan(
        1,
      ),
    )
    const zara = cards().find((card) => card.textContent?.includes('Zara Bautista'))!
    expect(zara).not.toHaveAttribute('data-state', 'conflict')
    expect(approve(...ZARA)).toBeEnabled()
    expect(deny(...ZARA)).toBeEnabled()
  })

  it('moves focus to the heading when nothing else is waiting', async () => {
    const open = await openPage({ waiting: [ZARA_WAITING] })
    await decideStale(open)
    await waitFor(() => expect(waitingHeading()).toHaveFocus())
    expect(cardNames()).toEqual(['Zara Bautista'])
  })

  it('shows the muted card even when the refresh still lists the request', async () => {
    const open = await openPage()
    await decideStale(open, { drop: false })
    const zara = cards().filter((card) => card.textContent?.includes('Zara Bautista'))
    expect(zara).toHaveLength(1)
    expect(zara[0]).toHaveAttribute('data-state', 'conflict')
  })

  it('says it was already decided when another manager decided it first, from the API’s status', async () => {
    const { user, fake } = await openPage()
    fake.dropWaiting(ZARA_WAITING.id, 'approved')
    await user.click(approve(...ZARA))
    await user.click(await screen.findByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(await screen.findByRole('alert')).toHaveTextContent('This request was already approved.')
  })

  it('holds the card the moment the 409 arrives, before the queue is read again', async () => {
    const { user, fake } = await openPage()
    fake.dropWaiting(ZARA_WAITING.id)
    await user.click(approve(...ZARA))
    const confirm = await screen.findByRole('button', { name: 'Approve' })
    // From here on the queue's read is held, so the card is seen between the refusal and the read.
    const release = gate()
    fake.state.holdRequests = (scope) => (scope === 'waiting' ? release.promise : undefined)
    await user.click(confirm)
    await waitFor(() => expect(fake.calls.decisions).toHaveLength(1))
    await waitFor(() =>
      expect(document.querySelector(`[data-request-id="${ZARA_WAITING.id}"]`)).toHaveAttribute(
        'data-state',
        'conflict',
      ),
    )
    release.open()
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(document.querySelector(`[data-request-id="${ZARA_WAITING.id}"]`)).not.toBeNull()
  })

  it('clears the held card on the next visit', async () => {
    const open = await openPage()
    await decideStale(open)
    await open.router.navigate('/time-off')
    await screen.findByRole('heading', { level: 1, name: 'Time off' })
    await open.router.navigate('/approvals')
    await screen.findByRole('heading', { level: 2, name: /^Waiting for you/ })
    await waitFor(() => expect(cardNames()).toEqual(['Priya Raman']))
  })
})

describe('Approvals: a decision that fails', () => {
  it('says so calmly, keeps the dialog open, and lets the manager try again', async () => {
    const { user, fake } = await openPage()
    fake.state.decideFailure = { status: 500, type: 'about:blank', detail: '' }
    await user.click(approve(...ZARA))
    await user.click(await screen.findByRole('button', { name: 'Approve' }))
    await waitFor(() =>
      expect(toast()).toHaveTextContent(
        'Couldn’t send that decision. Nothing was changed. Try again in a moment.',
      ),
    )
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled()
    expect(cardNames()).toEqual(['Zara Bautista', 'Priya Raman'])

    fake.state.decideFailure = null
    await user.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(cardNames()).toEqual(['Priya Raman'])
  })
})
