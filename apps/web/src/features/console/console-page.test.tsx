import { act, render, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { onlineManager } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import {
  DAY_TURNS,
  EMPTY_METRICS,
  T_1031_ANSWERED,
  T_1033_CARD,
  T_1038_INJECTION,
} from '@/app/gallery/fixtures/console'
import { installAssistantApi } from '@/test/fake-assistant'
import { handbookOverview } from '@/test/fake-handbook'
import { installFakeApi } from '@/test/fake-api'
import { installFakeConsole } from '@/test/fake-console'
import { server } from '@/test/msw'
import { ScoreboardSection } from './console-page'
import { renderApp } from '@/test/render-app'
import { signOutViaMenu, switchViaMenu } from '@/test/persona-menu'

// HR's AI Ops console at /console (Phase 7, Task 32).

type Persona = 'dana' | 'priya' | 'marcus'

function open(options: Parameters<typeof installFakeConsole>[0] = {}, persona: Persona = 'dana') {
  installFakeApi(persona)
  const fake = installFakeConsole(options)
  return { ...renderApp({ at: '/console' }), fake }
}

// The turn rows' buttons are named "10:31 AM, Employee, Oakland, CA, Answered"; the persona
// switcher's button also says "HR", so the roles are matched with the comma that follows the time.
const findPanel = () =>
  waitFor(() => {
    const panel = document.querySelector<HTMLElement>('[data-slot="trace-panel"]')
    if (!panel) throw new Error('no trace panel')
    return panel
  })

const rowButtons = () => screen.findAllByRole('button', { name: /^\d{1,2}:\d{2}\s?[AP]M,/ })

describe('the console: who can see it', () => {
  it.each(['priya', 'marcus'] as const)(
    'shows %s the Not found page, and asks for nothing',
    async (who) => {
      const { fake } = open({}, who)
      expect(
        await screen.findByRole('heading', { level: 1, name: "We couldn't find that page." }),
      ).toBeVisible()
      expect(fake.calls.turns).toEqual([])
      expect(fake.calls.metrics).toBe(0)
    },
  )
})

describe('the console', () => {
  it('shows the heading, the sandbox section with tiles and turns, and the scoreboard', async () => {
    const { fake } = open()
    expect(await screen.findByRole('heading', { level: 1, name: 'AI Ops console' })).toBeVisible()
    expect(
      screen.getByText(
        'What the assistant did on every turn in this sandbox. It never shows who asked or what they wrote.',
      ),
    ).toBeVisible()
    expect(screen.getByRole('heading', { level: 2, name: 'This sandbox' })).toBeVisible()
    expect(await screen.findByRole('group', { name: 'Time to first token' })).toBeVisible()
    expect(await rowButtons()).toHaveLength(8)
    expect(
      screen.getByText('Flagged by the safety check. Details are hidden to protect the person.'),
    ).toBeVisible()
    expect(screen.getByRole('heading', { level: 2, name: 'Eval scoreboard' })).toBeVisible()
    expect(fake.calls.turns).toEqual([null])
    expect(fake.calls.metrics).toBe(1)
  })

  it('shows the times in the viewer’s location’s zone', async () => {
    open()
    // The test Dana's location is Oakland (Pacific time): 16:31 UTC is 9:31 AM.
    expect(
      await screen.findByRole('button', {
        name: /^9:31\s?AM,\s?Employee,\s?Oakland, CA,\s?Answered/,
      }),
    ).toBeVisible()
  })

  it('has no link to code, a repository, an ADR, or any document', async () => {
    open()
    await rowButtons()
    expect(document.querySelectorAll('a[href^="http"]')).toHaveLength(0)
    const main = document.querySelector('main')!
    for (const link of within(main).queryAllByRole('link')) {
      expect(link.getAttribute('href')).not.toMatch(/github|adr|\.md|docs/i)
    }
  })

  it('opens a row’s trace without asking the server for anything', async () => {
    const { user, fake } = open()
    const [first] = await rowButtons()
    await screen.findByRole('group', { name: 'Time to first token' })
    const turnsBefore = fake.calls.turns.length
    const metricsBefore = fake.calls.metrics
    let requests = 0
    server.events.on('request:start', () => requests++)
    await user.click(first!)
    expect(await screen.findByText('Turn trace')).toBeVisible()
    expect(requests).toBe(0)
    expect(fake.calls.turns).toHaveLength(turnsBefore)
    expect(fake.calls.metrics).toBe(metricsBefore)
    server.events.removeAllListeners()
  })

  it('titles a section with its state when it is an addendum', async () => {
    const { user } = open({
      pages: { '': { items: [T_1031_ANSWERED], nextCursor: null } },
    })
    const [button] = await rowButtons()
    await user.click(button!)
    const panel = await findPanel()
    await waitFor(() => expect(within(panel).getByText('Sick leave (California)')).toBeVisible())
  })

  it('still works when the handbook fails: the IDs show without titles', async () => {
    installFakeApi('dana')
    installFakeConsole({ pages: { '': { items: [T_1031_ANSWERED], nextCursor: null } } })
    server.use(http.get(`${window.location.origin}/api/v1/handbook`, () => HttpResponse.error()))
    const { user } = renderApp({ at: '/console' })
    const [button] = await rowButtons()
    await user.click(button!)
    const panel = await findPanel()
    expect(within(panel).getByText('CA-4.3')).toBeVisible()
    expect(screen.getByRole('heading', { level: 1, name: 'AI Ops console' })).toBeVisible()
  })
})

describe('paging', () => {
  const FIRST = [T_1038_INJECTION, T_1033_CARD]
  const SECOND = [T_1031_ANSWERED]

  it('shows a "Show more turns" button after the list and appends the next page', async () => {
    const { user, fake } = open({
      pages: {
        '': { items: FIRST, nextCursor: 'page-2' },
        'page-2': { items: SECOND, nextCursor: null },
      },
    })
    expect(await rowButtons()).toHaveLength(2)
    await user.click(screen.getByRole('button', { name: 'Show more turns' }))
    await waitFor(async () => expect(await rowButtons()).toHaveLength(3))
    expect(fake.calls.turns).toEqual([null, 'page-2'])
    expect(screen.queryByRole('button', { name: 'Show more turns' })).not.toBeInTheDocument()
  })

  it('has no button when the first page is the last', async () => {
    open()
    await rowButtons()
    expect(screen.queryByRole('button', { name: 'Show more turns' })).not.toBeInTheDocument()
  })

  it('says a page could not be loaded, and keeps the button', async () => {
    const { user } = open({
      pages: { '': { items: FIRST, nextCursor: 'missing' } },
    })
    await rowButtons()
    server.use(
      http.get(`${window.location.origin}/api/v1/console/turns`, ({ request }) =>
        new URL(request.url).searchParams.get('cursor') === 'missing'
          ? HttpResponse.json({ title: 'x', status: 500 }, { status: 500 })
          : HttpResponse.json({ items: FIRST, nextCursor: 'missing' }),
      ),
    )
    await user.click(screen.getByRole('button', { name: 'Show more turns' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('More turns couldn’t be loaded')
    expect(screen.getByRole('button', { name: 'Show more turns' })).toBeVisible()
  })
})

describe('the states', () => {
  it('is empty in a new sandbox: the empty state, "Ask a question" to /ask, and the scoreboard', async () => {
    const { user, router } = open({
      metrics: EMPTY_METRICS,
      pages: { '': { items: [], nextCursor: null } },
    })
    expect(
      await screen.findByText('No questions yet in this sandbox. Ask something, or take the tour.'),
    ).toBeVisible()
    expect(screen.getByRole('heading', { level: 2, name: 'Eval scoreboard' })).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Ask a question' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/ask'))
  })

  it('opens the tour’s "Start the tour?" dialog from the empty state', async () => {
    const { user } = open({
      metrics: EMPTY_METRICS,
      pages: { '': { items: [], nextCursor: null } },
    })
    await user.click(await screen.findByRole('button', { name: 'Take the tour' }))
    const dialog = await screen.findByRole('alertdialog', { name: 'Start the tour?' })
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toHaveFocus()
  })

  it('does not offer the tour while a persona switch is in flight', async () => {
    const { user } = open({
      metrics: EMPTY_METRICS,
      pages: { '': { items: [], nextCursor: null } },
    })
    const tour = await screen.findByRole('button', { name: 'Take the tour' })
    expect(tour).toBeEnabled()
    server.use(
      http.put(
        `${window.location.origin}/api/v1/session/persona`,
        () => new Promise<Response>(() => {}),
      ),
    )
    await switchViaMenu(user, 'Marcus')
    await screen.findByRole('button', { name: /^Switching to Marcus/ })
    expect(screen.getByRole('button', { name: 'Take the tour' })).toBeDisabled()
  })

  it('does not offer the tour while a sign out is in flight', async () => {
    const { user } = open({
      metrics: EMPTY_METRICS,
      pages: { '': { items: [], nextCursor: null } },
    })
    expect(await screen.findByRole('button', { name: 'Take the tour' })).toBeEnabled()
    server.use(
      http.delete(
        `${window.location.origin}/api/v1/session`,
        () => new Promise<Response>(() => {}),
      ),
    )
    await signOutViaMenu(user)
    await screen.findByRole('button', { name: /^Signing out/ })
    expect(screen.getByRole('button', { name: 'Take the tour' })).toBeDisabled()
  })

  it('shows skeletons while loading, busy and announced, with the scoreboard shown', async () => {
    installFakeApi('dana')
    installFakeConsole()
    const gate = new Promise<void>(() => {})
    server.use(
      http.get(`${window.location.origin}/api/v1/console/metrics`, async () => {
        await gate
        return HttpResponse.json({})
      }),
    )
    renderApp({ at: '/console' })
    const section = (
      await screen.findByRole('heading', { level: 2, name: 'This sandbox' })
    ).closest('section')!
    expect(section).toHaveAttribute('aria-busy', 'true')
    // Exactly one live region says it, in the whole page (the table's).
    await waitFor(() =>
      expect(
        screen
          .getAllByRole('status')
          .filter((el) => el.textContent === 'Loading the sandbox figures'),
      ).toHaveLength(1),
    )
    expect(within(section).queryByRole('status')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Eval scoreboard' })).toBeVisible()
    expect(
      screen.queryByRole('button', { name: /^\d{1,2}:\d{2}\s?[AP]M,/ }),
    ).not.toBeInTheDocument()
  })

  it('shows the error with the reference, keeps the scoreboard, and Retry reads both again', async () => {
    const { user, fake } = open({ turnsStatus: 500 })
    expect(
      await screen.findByRole('heading', { name: 'Something went wrong on our side.' }),
    ).toBeVisible()
    expect(screen.getByText('c41e8b07'.repeat(4))).toBeVisible()
    expect(screen.getByRole('heading', { level: 2, name: 'Eval scoreboard' })).toBeVisible()
    fake.recover()
    // Hold the next read open, so the section's busy state can be seen.
    let release!: () => void
    const gate = new Promise<void>((resolve) => (release = resolve))
    server.use(
      http.get(`${window.location.origin}/api/v1/console/turns`, async () => {
        await gate
        return HttpResponse.json({ items: DAY_TURNS, nextCursor: null })
      }),
    )
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    // A load with nothing to show goes back to pending, so the section is busy again until the
    // reads finish, and the error is not left standing.
    const section = screen
      .getByRole('heading', { level: 2, name: 'This sandbox' })
      .closest('section')!
    await waitFor(() => expect(section).toHaveAttribute('aria-busy', 'true'))
    expect(screen.queryByRole('heading', { name: 'Something went wrong on our side.' })).toBeNull()
    release()
    expect(await rowButtons()).toHaveLength(8)
    expect(screen.queryByRole('heading', { name: 'Something went wrong on our side.' })).toBeNull()
  })

  it('names the failed read in the reference, not a stale background error of the other', async () => {
    // The turns loaded; the figures' first read failed. Then the turns' background read fails too:
    // that stale error must not be the reference for the figures' failure.
    const { queryClient, fake } = open({ metricsStatus: 500 })
    await screen.findByRole('heading', { name: 'Something went wrong on our side.' })
    expect(screen.getByText('d52f9c18'.repeat(4))).toBeVisible()
    fake.set({ turnsStatus: 500 })
    await act(() => queryClient.refetchQueries({ queryKey: ['/api/v1/console/turns'] }))
    await waitFor(() => expect(queryClient.isFetching()).toBe(0))
    expect(screen.getByText('d52f9c18'.repeat(4))).toBeVisible()
    expect(screen.queryByText('c41e8b07'.repeat(4))).toBeNull()
  })

  it('shows the error when only the figures fail', async () => {
    open({ metricsStatus: 500 })
    expect(
      await screen.findByRole('heading', { name: 'Something went wrong on our side.' }),
    ).toBeVisible()
  })
})

describe('a read again', () => {
  const FIRST = [T_1038_INJECTION, T_1033_CARD]
  const SECOND = [T_1031_ANSWERED]
  const TWO_PAGES = {
    '': { items: FIRST, nextCursor: 'page-2' },
    'page-2': { items: SECOND, nextCursor: null },
  }

  async function withPageTwo() {
    const view = open({ pages: TWO_PAGES })
    await rowButtons()
    await view.user.click(screen.getByRole('button', { name: 'Show more turns' }))
    await waitFor(async () => expect(await rowButtons()).toHaveLength(3))
    return view
  }

  it('keeps the rows when a background read fails', async () => {
    const { queryClient, fake } = await withPageTwo()
    fake.set({ turnsStatus: 500, metricsStatus: 500 })
    await queryClient.invalidateQueries()
    await waitFor(() => expect(fake.calls.turns.length).toBeGreaterThan(2))
    await waitFor(() => expect(queryClient.isFetching()).toBe(0))
    expect(screen.queryByRole('heading', { name: 'Something went wrong on our side.' })).toBeNull()
    expect(await rowButtons()).toHaveLength(3)
  })

  it('drops the held pages when the first page changed, and brings the button back', async () => {
    const { queryClient, fake } = await withPageTwo()
    fake.set({ pages: { ...TWO_PAGES, '': { items: [T_1038_INJECTION], nextCursor: 'page-2' } } })
    await queryClient.invalidateQueries()
    await waitFor(async () => expect(await rowButtons()).toHaveLength(1))
    expect(screen.getByRole('button', { name: 'Show more turns' })).toBeVisible()
  })

  it('keeps the held pages when the first page is the same', async () => {
    const { queryClient, fake } = await withPageTwo()
    const before = fake.calls.turns.length
    await queryClient.invalidateQueries()
    await waitFor(() => expect(fake.calls.turns.length).toBeGreaterThan(before))
    await waitFor(() => expect(queryClient.isFetching()).toBe(0))
    expect(await rowButtons()).toHaveLength(3)
    expect(screen.queryByRole('button', { name: 'Show more turns' })).not.toBeInTheDocument()
  })

  it('does not read again on a window refocus, so the held pages stay', async () => {
    const { fake } = await withPageTwo()
    const turnsBefore = fake.calls.turns.length
    const metricsBefore = fake.calls.metrics
    // A new turn since: a read now would change the first page and drop the held one.
    fake.set({ pages: { ...TWO_PAGES, '': { items: [T_1038_INJECTION], nextCursor: 'page-2' } } })
    act(() => {
      window.dispatchEvent(new Event('visibilitychange'))
    })
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(fake.calls.turns).toHaveLength(turnsBefore)
    expect(fake.calls.metrics).toBe(metricsBefore)
    expect(await rowButtons()).toHaveLength(3)
  })

  it('does not read again on a reconnect, so the held pages stay', async () => {
    const { fake } = await withPageTwo()
    const turnsBefore = fake.calls.turns.length
    const metricsBefore = fake.calls.metrics
    fake.set({ pages: { ...TWO_PAGES, '': { items: [T_1038_INJECTION], nextCursor: 'page-2' } } })
    act(() => {
      onlineManager.setOnline(false)
    })
    act(() => {
      onlineManager.setOnline(true)
    })
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(fake.calls.turns).toHaveLength(turnsBefore)
    expect(fake.calls.metrics).toBe(metricsBefore)
    expect(await rowButtons()).toHaveLength(3)
  })

  it('clears a failed-page message when the first page changed', async () => {
    const { user, queryClient, fake } = open({
      pages: TWO_PAGES,
      failCursor: 'page-2',
    })
    await rowButtons()
    await user.click(screen.getByRole('button', { name: 'Show more turns' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('More turns couldn’t be loaded')
    fake.set({ pages: { ...TWO_PAGES, '': { items: [T_1038_INJECTION], nextCursor: 'page-2' } } })
    await queryClient.invalidateQueries()
    await waitFor(async () => expect(await rowButtons()).toHaveLength(1))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('the console and the handbook', () => {
  it('uses the handbook the shell already read for the section titles, not a second download', async () => {
    installFakeApi('dana')
    installAssistantApi()
    installFakeConsole()
    let reads = 0
    server.use(
      http.get(`${window.location.origin}/api/v1/handbook`, () => {
        reads += 1
        return HttpResponse.json(handbookOverview('priya'))
      }),
    )
    const { router } = renderApp({ at: '/ask' })
    await waitFor(() => expect(reads).toBe(1))
    await act(() => router.navigate('/console'))
    expect(await rowButtons()).toHaveLength(8)
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(reads).toBe(1)
  })
})

describe('the scoreboard section', () => {
  it('shows one plain line, and does not throw, when the generated file has the wrong shape', () => {
    render(<ScoreboardSection data={{ boards: 'nope' }} />)
    expect(screen.getByText('The eval scoreboard can’t be shown right now.')).toBeVisible()
    expect(screen.queryByRole('heading', { level: 2, name: 'Eval scoreboard' })).toBeNull()
  })
})
