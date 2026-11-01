import { act, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getGetMeQueryKey } from '@/api/generated'
import { getSessionStatus } from '@/app/session-status'
import { useChatStore } from '@/features/chat/store'
import { accessibleNameOf } from '@/test/accessible-name'
import { installFakeApi } from '@/test/fake-api'
import { installFakeHandbook } from '@/test/fake-handbook'
import { installFakeTimeOff } from '@/test/fake-time-off'
import { PRIYA_WAITING } from '@/app/gallery/fixtures/timeoff'
import { DIRECTORY_PEOPLE, installFakeDirectory } from '@/test/fake-directory'
import { meFor } from '@/test/fixtures'
import { useShellLayout } from './shell-layout-store'
import { useShellToast } from './toast-store'
import { personaSwitcher, signOutViaMenu, switchViaMenu } from '@/test/persona-menu'
import { server } from '@/test/msw'
import { renderApp } from '@/test/render-app'

const SWITCH = () => `${window.location.origin}/api/v1/session/persona`
const END = () => `${window.location.origin}/api/v1/session`
const LANDING = 'Your open-door policy, now always open.'
const PRIYA = 'Priya Raman, Visual Merchandiser. Current persona. Switch persona'
const MARCUS = 'Marcus Bell, Store Manager. Current persona. Switch persona'

const toast = () => document.querySelector<HTMLElement>('[data-slot="toast"]')
const hoursFromNow = (hours: number) => new Date(Date.now() + hours * 3_600_000).toISOString()

function gate() {
  let resolve = () => {}
  const promise = new Promise<void>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

function failOnce(url: string, method: 'put' | 'delete') {
  server.use(
    http[method](
      url,
      () =>
        HttpResponse.json(
          { type: 'about:blank', title: 'Boom', status: 500, instance: '/x' },
          { status: 500 },
        ),
      { once: true },
    ),
  )
}

beforeEach(() => {
  sessionStorage.clear()
})

describe('the shell: layout', () => {
  it('has the sidebar, one main landmark, and the rail', async () => {
    installFakeApi('priya')
    renderApp({ at: '/ask' })
    const sidebar = await screen.findByRole('complementary', { name: 'Sidebar' })
    expect(within(sidebar).getByText('Open Door')).toBeInTheDocument()
    expect(within(sidebar).getByText('Juniper Row')).toBeInTheDocument()
    expect(screen.getAllByRole('main')).toHaveLength(1)
    expect(screen.getByRole('complementary', { name: 'Sandbox status' })).toBeInTheDocument()
  })

  it('has no rail on the directory or a profile, and shows the indicator in the page header', async () => {
    installFakeApi('priya')
    installFakeDirectory('priya')
    const { router } = renderApp({ at: '/directory' })
    const main = await screen.findByRole('main')
    await screen.findByRole('list', { name: 'People' })
    expect(screen.queryByRole('complementary', { name: 'Sandbox status' })).not.toBeInTheDocument()
    const inList = within(main).getByText(/^Sandbox resets in/)
    expect(inList.closest('header')).not.toBeNull()
    // The top bar carries it below 760 px, so the header's hides there.
    expect(inList.closest('[data-slot="sandbox-indicator"]')).toHaveClass('max-[760px]:hidden')

    await act(() => router.navigate(`/directory/${DIRECTORY_PEOPLE[0]!.id}`))
    await screen.findByRole('heading', { level: 1, name: /\w/ })
    expect(screen.queryByRole('complementary', { name: 'Sandbox status' })).not.toBeInTheDocument()
    expect(
      within(screen.getByRole('main'))
        .getByText(/^Sandbox resets in/)
        .closest('header'),
    ).not.toBeNull()
  })

  it('keeps exactly one main on the pages, the profile, and not found', async () => {
    installFakeApi('priya')
    const { router } = renderApp({ at: '/ask' })
    await screen.findByRole('complementary', { name: 'Sidebar' })
    for (const path of [
      '/directory',
      '/directory/0f8fad5b-d9cb-469f-a165-70867728950e',
      '/nowhere',
    ]) {
      await act(() => router.navigate(path))
      expect(screen.getAllByRole('main')).toHaveLength(1)
    }
  })

  it('lists the navigation for this person, in the main navigation', async () => {
    installFakeApi('priya')
    renderApp({ at: '/ask' })
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    expect(
      within(nav)
        .getAllByRole('link')
        .map((a) => a.textContent),
    ).toEqual(['Ask', 'Time off', 'My cases', 'Directory', 'Handbook'])
  })

  it('marks the page you are on, and Directory for a profile below it', async () => {
    installFakeApi('priya')
    const { router } = renderApp({ at: '/ask' })
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    expect(within(nav).getByRole('link', { name: 'Ask' })).toHaveAttribute('aria-current', 'page')
    await act(() => router.navigate('/directory/0f8fad5b-d9cb-469f-a165-70867728950e'))
    expect(within(nav).getByRole('link', { name: 'Directory' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(within(nav).getByRole('link', { name: 'Ask' })).not.toHaveAttribute('aria-current')
  })

  it('marks no item current on the not-found page', async () => {
    installFakeApi('priya')
    renderApp({ at: '/nowhere' })
    await screen.findByRole('heading', { level: 1, name: "We couldn't find that page." })
    const nav = screen.getByRole('navigation', { name: 'Main' })
    for (const link of within(nav).getAllByRole('link')) {
      expect(link).not.toHaveAttribute('aria-current')
    }
  })

  it('names the signed-in person in the switcher', async () => {
    installFakeApi('priya')
    renderApp({ at: '/ask' })
    await screen.findByRole('complementary', { name: 'Sidebar' })
    expect(personaSwitcher()).toHaveAccessibleName(PRIYA)
  })

  it('shows the sandbox indicator in the top bar on a narrow screen and in the rail otherwise', async () => {
    installFakeApi('priya')
    renderApp({ at: '/ask' })
    const bar = await screen.findByRole('complementary', { name: 'Sidebar' })
    const rail = screen.getByRole('complementary', { name: 'Sandbox status' })
    const inBar = within(bar)
      .getByText(/^Sandbox resets in/)
      .closest('[data-slot="sandbox-indicator"]')
    const inRail = within(rail)
      .getByText(/^Sandbox resets in/)
      .closest('[data-slot="sandbox-indicator"]')
    // One is shown at a time: the bar's below 760 px, the rail's above it.
    expect(inBar).toHaveClass('hidden', 'max-[760px]:inline-flex')
    expect(inRail).toHaveClass('max-[760px]:hidden')
  })

  it('puts the rail below the content on a narrow screen', async () => {
    installFakeApi('priya')
    renderApp({ at: '/ask' })
    const rail = await screen.findByRole('complementary', { name: 'Sandbox status' })
    expect(rail.parentElement).toHaveClass('max-[760px]:grid-cols-1')
  })

  it('shows "Handbook updated" in the at-a-glance list, as a link to the handbook', async () => {
    installFakeApi('priya')
    renderApp({ at: '/ask' })
    const rail = await screen.findByRole('complementary', { name: 'Sandbox status' })
    const glance = await within(rail).findByRole('region', { name: 'At a glance' })
    const link = within(glance).getByRole('link', {
      name: 'Sep 12 Handbook updated. Open Handbook',
    })
    expect(link).toHaveAttribute('href', '/handbook')
    expect(within(link).getByText('Sep 12')).toBeVisible()
    expect(within(link).getByText('Handbook updated')).toBeVisible()
  })

  it('shows the Handbook item in the sidebar', async () => {
    installFakeApi('priya')
    renderApp({ at: '/ask' })
    expect(await screen.findByRole('link', { name: 'Handbook' })).toHaveAttribute(
      'href',
      '/handbook',
    )
  })

  it('leaves out only the handbook figure when the handbook fails, and the page still works', async () => {
    installFakeApi('priya')
    let hits = 0
    server.use(
      http.get(`${window.location.origin}/api/v1/handbook`, () => {
        hits += 1
        return HttpResponse.json(
          { type: 'about:blank', title: 'Boom', status: 500, instance: '/x' },
          { status: 500 },
        )
      }),
    )
    const { queryClient } = renderApp({ at: '/ask' })
    const rail = await screen.findByRole('complementary', { name: 'Sandbox status' })
    // Wait until the failing request was made and the query gave up on it.
    await waitFor(() => expect(hits).toBeGreaterThan(0))
    await waitFor(() => expect(queryClient.isFetching({ queryKey: ['/api/v1/handbook'] })).toBe(0))
    await waitFor(() =>
      expect(queryClient.getQueryState(['/api/v1/handbook', 'glance'])?.status).toBe('error'),
    )
    expect(
      screen.getByRole('heading', {
        level: 1,
        name: /^Good (morning|afternoon|evening), Priya\.$/,
      }),
    ).toBeVisible()
    const glance = await within(rail).findByRole('region', { name: 'At a glance' })
    expect(
      within(glance)
        .getAllByRole('link')
        .map((link) => accessibleNameOf(link)),
    ).toEqual(['92 hours PTO available. Open Time off', '0 requests pending. Open Time off'])
  })

  it('leaves the rail empty, and hidden below 760 px, when both the handbook and the summary fail', async () => {
    installFakeApi('priya')
    const boom = () =>
      HttpResponse.json(
        { type: 'about:blank', title: 'Boom', status: 500, instance: '/x' },
        { status: 500 },
      )
    server.use(
      http.get(`${window.location.origin}/api/v1/handbook`, boom),
      http.get(`${window.location.origin}/api/v1/time-off/summary`, boom),
    )
    const { queryClient } = renderApp({ at: '/ask' })
    const rail = await screen.findByRole('complementary', { name: 'Sandbox status' })
    await waitFor(() =>
      expect(queryClient.getQueryState(['/api/v1/handbook', 'glance'])?.status).toBe('error'),
    )
    await waitFor(() =>
      expect(queryClient.getQueryState(['/api/v1/time-off/summary'])?.status).toBe('error'),
    )
    expect(within(rail).queryByRole('region', { name: 'At a glance' })).not.toBeInTheDocument()
    // With nothing to list, the rail is hidden on a narrow screen: the indicator is in the top bar.
    expect(rail).toHaveClass('max-[760px]:hidden')
  })

  it('puts the toast viewport inside the content sheet', async () => {
    installFakeApi('priya')
    renderApp({ at: '/ask' })
    await screen.findByRole('complementary', { name: 'Sidebar' })
    const viewport = document.querySelector('[data-slot="toast-viewport"]')!
    expect(viewport.closest('[data-slot="shell-sheet"]')).not.toBeNull()
    expect(viewport).toHaveClass('absolute')
  })
})

describe('the shell: the navigation scrolls on a narrow screen', () => {
  it('fades its edge only while there is more to scroll to', async () => {
    vi.spyOn(Element.prototype, 'scrollWidth', 'get').mockReturnValue(600)
    vi.spyOn(Element.prototype, 'clientWidth', 'get').mockReturnValue(300)
    installFakeApi('priya')
    renderApp({ at: '/ask' })
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    await waitFor(() => expect(nav).toHaveAttribute('data-more', 'true'))
    expect(nav).toHaveClass('max-[760px]:overflow-x-auto')

    Object.defineProperty(nav, 'scrollLeft', { value: 300, configurable: true })
    act(() => {
      nav.dispatchEvent(new Event('scroll'))
    })
    await waitFor(() => expect(nav).toHaveAttribute('data-more', 'false'))
  })

  it('shows no fade when everything fits', async () => {
    installFakeApi('priya')
    renderApp({ at: '/ask' })
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    expect(nav).toHaveAttribute('data-more', 'false')
  })
})

describe('the shell: switching', () => {
  it('shows "Switching to Marcus…", which the menu will not open on, then lands on /ask as Marcus with the toast', async () => {
    const api = installFakeApi('priya')
    const hold = gate()
    // Every /me after the first waits for this gate, so Marcus can only come from the switch's own
    // answer being stored, not from a refetch.
    const holdMe = gate()
    let holdingMe = false
    server.use(
      http.get(`${window.location.origin}/api/v1/me`, async () => {
        if (holdingMe) await holdMe.promise
        return HttpResponse.json(meFor(api.signedInAs()!))
      }),
      http.put(SWITCH(), async () => {
        await hold.promise
        api.signIn('marcus')
        return HttpResponse.json(meFor('marcus'))
      }),
    )
    const { user, router, queryClient } = renderApp({ at: '/directory' })
    await screen.findByRole('complementary', { name: 'Sidebar' })
    holdingMe = true
    useChatStore.getState().setDraft('a half-typed question')
    const countBefore = getSessionStatus().resetCount

    await switchViaMenu(user, 'Marcus')
    const busy = await screen.findByRole('button', { name: 'Switching to Marcus…' })
    expect(busy).toHaveAttribute('aria-disabled', 'true')
    await user.click(busy)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(toast()).toBeNull()

    hold.resolve()
    await waitFor(() => expect(personaSwitcher()).toHaveAccessibleName(MARCUS))
    // The identity was reset, the new person stored, and the visitor sent to /ask.
    expect(getSessionStatus().resetCount).toBeGreaterThan(countBefore)
    expect(queryClient.getQueryData<{ givenName: string }>(getGetMeQueryKey())?.givenName).toBe(
      'Marcus',
    )
    expect(router.state.location.pathname).toBe('/ask')
    // The conversation is empty.
    expect(useChatStore.getState().draft).toBe('')
    expect(useChatStore.getState().status).toBe('idle')
    // The toast renders after the identity reset remounts the shell, so it can come a moment after
    // the switcher's new name; the app doesn't promise the two appear together.
    await waitFor(() => expect(toast()).toHaveTextContent('Now viewing as Marcus Bell.'))
    expect(within(toast()!).getByRole('button', { name: 'Dismiss' })).toBeInTheDocument()
    holdMe.resolve()
  })

  it('closes the toast with its button', async () => {
    installFakeApi('priya')
    const { user } = renderApp({ at: '/ask' })
    await screen.findByRole('complementary', { name: 'Sidebar' })
    await switchViaMenu(user, 'Marcus')
    await waitFor(() => expect(toast()).not.toBeNull())
    await user.click(within(toast()!).getByRole('button', { name: 'Dismiss' }))
    await waitFor(() => expect(toast()).toBeNull())
  })

  describe('with fake timers', () => {
    beforeEach(() => {
      vi.useFakeTimers({ shouldAdvanceTime: true })
    })
    afterEach(() => {
      vi.useRealTimers()
    })

    it('closes the toast by itself after 6 seconds', async () => {
      installFakeApi('priya')
      const { user } = renderApp({ at: '/ask' })
      await screen.findByRole('complementary', { name: 'Sidebar' })
      await switchViaMenu(user, 'Marcus')
      await waitFor(() => expect(toast()).not.toBeNull())
      await act(() => vi.advanceTimersByTimeAsync(5_000))
      expect(toast()).not.toBeNull()
      await act(() => vi.advanceTimersByTimeAsync(1_500))
      await waitFor(() => expect(toast()).toBeNull())
    })
  })

  it('keeps the old person and shows an error when the switch fails, and the switcher works again', async () => {
    const api = installFakeApi('priya')
    failOnce(SWITCH(), 'put')
    const { user } = renderApp({ at: '/ask' })
    await screen.findByRole('complementary', { name: 'Sidebar' })
    await switchViaMenu(user, 'Marcus')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent("We couldn't switch to Marcus.")
    expect(toast()).toBeNull()
    expect(personaSwitcher()).toHaveAccessibleName(PRIYA)
    expect(personaSwitcher()).not.toHaveAttribute('aria-disabled')
    expect(api.signedInAs()).toBe('priya')

    // Retry sends the same switch again.
    await user.click(within(alert).getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(personaSwitcher()).toHaveAccessibleName(MARCUS))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('does nothing when the current person is chosen', async () => {
    let calls = 0
    installFakeApi('priya')
    server.use(
      http.put(SWITCH(), () => {
        calls++
        return new HttpResponse(null, { status: 500 })
      }),
    )
    const { user } = renderApp({ at: '/ask' })
    await screen.findByRole('complementary', { name: 'Sidebar' })
    await switchViaMenu(user, 'Priya')
    expect(calls).toBe(0)
  })
})

describe('the shell: signing out', () => {
  it('goes to the landing page with the state cleared', async () => {
    const api = installFakeApi('priya')
    const { user, router, queryClient } = renderApp({ at: '/ask' })
    await screen.findByRole('complementary', { name: 'Sidebar' })
    useChatStore.getState().setDraft('a half-typed question')
    const countBefore = getSessionStatus().resetCount

    await signOutViaMenu(user)
    await screen.findByRole('heading', { level: 1, name: LANDING })
    expect(router.state.location.pathname).toBe('/')
    expect(api.signedInAs()).toBeNull()
    expect(getSessionStatus().resetCount).toBeGreaterThan(countBefore)
    expect(queryClient.getQueryData(getGetMeQueryKey())).toBeUndefined()
    expect(useChatStore.getState().draft).toBe('')
  })

  it('shows "Signing out…" while it runs, and the menu will not open', async () => {
    const api = installFakeApi('priya')
    const hold = gate()
    server.use(
      http.delete(END(), async () => {
        await hold.promise
        api.expire()
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const { user } = renderApp({ at: '/ask' })
    await screen.findByRole('complementary', { name: 'Sidebar' })
    await signOutViaMenu(user)
    const busy = await screen.findByRole('button', { name: 'Signing out…' })
    await user.click(busy)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    hold.resolve()
    await screen.findByRole('heading', { level: 1, name: LANDING })
  })

  it('stays signed in and shows an error when signing out fails', async () => {
    const api = installFakeApi('priya')
    failOnce(END(), 'delete')
    const { user, router } = renderApp({ at: '/ask' })
    await screen.findByRole('complementary', { name: 'Sidebar' })
    useChatStore.getState().setDraft('keep me')
    await signOutViaMenu(user)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent("We couldn't sign you out.")
    expect(router.state.location.pathname).toBe('/ask')
    expect(api.signedInAs()).toBe('priya')
    expect(personaSwitcher()).toHaveAccessibleName(PRIYA)
    expect(personaSwitcher()).not.toHaveAttribute('aria-disabled')
    expect(useChatStore.getState().draft).toBe('keep me')

    await user.click(within(alert).getByRole('button', { name: 'Retry' }))
    await screen.findByRole('heading', { level: 1, name: LANDING })
  })
})

describe('the shell: the countdown and the banner', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  const indicators = () => screen.getAllByText(/^Sandbox resets in/).map((el) => el.textContent)
  const banner = () => document.querySelector('[data-slot="banner"]')

  it('shows whole hours, and no banner, with more than 3 hours left', async () => {
    const api = installFakeApi('priya')
    api.setExpiry(hoursFromNow(21.5))
    renderApp({ at: '/ask' })
    await screen.findByRole('complementary', { name: 'Sidebar' })
    expect(indicators()).toEqual(['Sandbox resets in 21 h', 'Sandbox resets in 21 h'])
    expect(banner()).toBeNull()
  })

  it('shows hours and minutes and the banner under 3 hours, and counts down each minute', async () => {
    const api = installFakeApi('priya')
    api.setExpiry(new Date(Date.now() + (2 * 60 + 50) * 60_000 + 30_000).toISOString())
    renderApp({ at: '/ask' })
    await screen.findByRole('complementary', { name: 'Sidebar' })
    expect(indicators()).toEqual(['Sandbox resets in 2 h 50 min', 'Sandbox resets in 2 h 50 min'])
    expect(banner()).toHaveTextContent(
      "This sandbox resets in 2 h 50 min. Everything you've done here will be cleared.",
    )

    await act(() => vi.advanceTimersByTimeAsync(60_000))
    expect(indicators()).toEqual(['Sandbox resets in 2 h 49 min', 'Sandbox resets in 2 h 49 min'])
    expect(banner()).toHaveTextContent('This sandbox resets in 2 h 49 min.')
    await act(() => vi.advanceTimersByTimeAsync(5 * 60_000))
    expect(banner()).toHaveTextContent('This sandbox resets in 2 h 44 min.')
  })

  it('shows the banner once the countdown reaches 3 hours', async () => {
    const api = installFakeApi('priya')
    api.setExpiry(new Date(Date.now() + 3 * 3_600_000 + 30_000).toISOString())
    renderApp({ at: '/ask' })
    await screen.findByRole('complementary', { name: 'Sidebar' })
    expect(banner()).toBeNull()
    await act(() => vi.advanceTimersByTimeAsync(60_000))
    expect(banner()).not.toBeNull()
  })

  it('remembers a dismissal for the session, under a key that holds the expiry', async () => {
    const api = installFakeApi('priya')
    const expiry = hoursFromNow(2.5)
    api.setExpiry(expiry)
    const { user, router } = renderApp({ at: '/ask' })
    await screen.findByRole('complementary', { name: 'Sidebar' })
    await user.click(screen.getByRole('button', { name: 'Dismiss for this session' }))
    expect(banner()).toBeNull()
    const keys = Object.keys(sessionStorage)
    expect(keys).toHaveLength(1)
    expect(keys[0]).toContain(expiry)
    expect(localStorage.length).toBe(0)
    // Still dismissed after moving around.
    await act(() => router.navigate('/directory'))
    expect(banner()).toBeNull()
  })

  it('shows the banner again for a new sandbox, with a new expiry', async () => {
    const api = installFakeApi('priya')
    api.setExpiry(hoursFromNow(2.5))
    const { user } = renderApp({ at: '/ask' })
    await screen.findByRole('complementary', { name: 'Sidebar' })
    await user.click(screen.getByRole('button', { name: 'Dismiss for this session' }))
    expect(banner()).toBeNull()

    await signOutViaMenu(user)
    await screen.findByRole('heading', { level: 1, name: LANDING })
    api.setExpiry(hoursFromNow(2.9))
    await user.click(await screen.findByRole('button', { name: /^Priya / }))
    await screen.findByRole('complementary', { name: 'Sidebar' })
    expect(banner()).not.toBeNull()
  })

  it('keeps a dismissal when switching person in the same sandbox', async () => {
    const api = installFakeApi('priya')
    api.setExpiry(hoursFromNow(2.5))
    const { user } = renderApp({ at: '/ask' })
    await screen.findByRole('complementary', { name: 'Sidebar' })
    await user.click(screen.getByRole('button', { name: 'Dismiss for this session' }))
    await switchViaMenu(user, 'Marcus')
    await waitFor(() => expect(personaSwitcher()).toHaveAccessibleName(MARCUS))
    expect(banner()).toBeNull()
  })
})

describe('the shell: review fixes', () => {
  const sidebarReady = () => screen.findByRole('complementary', { name: 'Sidebar' })
  const marcusToast = () => toast()?.textContent?.includes('Now viewing as Marcus Bell.')

  it('names the sidebar, and leaves no unnamed banner landmark', async () => {
    installFakeApi('priya')
    renderApp({ at: '/ask' })
    const sidebar = await sidebarReady()
    expect(within(sidebar).getByRole('navigation', { name: 'Main' })).toBeInTheDocument()
    expect(within(sidebar).getByRole('button', { name: /Switch persona$/ })).toBeInTheDocument()
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
  })

  it('drops the toast when another tab changes the person while it is up', async () => {
    const api = installFakeApi('priya')
    const { user, queryClient } = renderApp({ at: '/ask' })
    await sidebarReady()
    await switchViaMenu(user, 'Marcus')
    await waitFor(() => expect(marcusToast()).toBe(true))

    api.signIn('dana')
    await act(() => queryClient.invalidateQueries({ queryKey: getGetMeQueryKey() }))
    await waitFor(() =>
      expect(personaSwitcher()).toHaveAccessibleName(
        'Dana Whitfield, HR Business Partner. Current persona. Switch persona',
      ),
    )
    expect(toast()).toBeNull()
    // Gone from the store too, not only hidden from Dana by the check on who it is for.
    expect(useShellToast.getState().message).toBeNull()
  })

  it('drops the toast when the sandbox expires and a new one starts as someone else', async () => {
    const api = installFakeApi('priya')
    const { user, queryClient } = renderApp({ at: '/ask' })
    await sidebarReady()
    await switchViaMenu(user, 'Marcus')
    await waitFor(() => expect(marcusToast()).toBe(true))

    api.expire()
    await act(() => queryClient.invalidateQueries())
    await user.click(await screen.findByRole('button', { name: 'Choose who to be' }))
    await user.click(await screen.findByRole('button', { name: /^Priya / }))
    await sidebarReady()
    expect(personaSwitcher()).toHaveAccessibleName(PRIYA)
    expect(toast()).toBeNull()
    expect(useShellToast.getState().message).toBeNull()
  })

  it('shows a toast only to the person it names', async () => {
    installFakeApi('priya')
    renderApp({ at: '/ask' })
    await sidebarReady()
    act(() => useShellToast.getState().show('Now viewing as Marcus Bell.', meFor('marcus').id))
    expect(toast()).toBeNull()
    act(() => useShellToast.getState().show('Now viewing as Priya Raman.', meFor('priya').id))
    expect(toast()).toHaveTextContent('Now viewing as Priya Raman.')
  })

  describe('the expiry banner as a status', () => {
    beforeEach(() => {
      vi.useFakeTimers({ shouldAdvanceTime: true })
    })
    afterEach(() => {
      vi.useRealTimers()
    })
    const live = () =>
      screen.getAllByRole('status').filter((el) => /This sandbox resets/.test(el.textContent ?? ''))

    it('is announced once, by a region that was already there, and never again as it counts down', async () => {
      const api = installFakeApi('priya')
      api.setExpiry(new Date(Date.now() + (2 * 60 + 50) * 60_000 + 30_000).toISOString())
      renderApp({ at: '/ask' })
      await sidebarReady()
      const banner = document.querySelector('[data-slot="banner"]')!
      expect(banner.tagName).not.toBe('OUTPUT')
      expect(banner).toHaveTextContent('This sandbox resets in 2 h 50 min.')
      await waitFor(() => expect(live()).toHaveLength(1))
      expect(live()[0]).not.toContainElement(banner as HTMLElement)
      expect(live()[0]).toHaveTextContent('This sandbox resets in 2 h 50 min.')

      await act(() => vi.advanceTimersByTimeAsync(60_000))
      expect(banner).toHaveTextContent('This sandbox resets in 2 h 49 min.')
      expect(live()[0]).toHaveTextContent('This sandbox resets in 2 h 50 min.')
    })

    it('has an empty status region before the banner appears', async () => {
      const api = installFakeApi('priya')
      api.setExpiry(new Date(Date.now() + 5 * 3_600_000).toISOString())
      renderApp({ at: '/ask' })
      await sidebarReady()
      expect(live()).toHaveLength(0)
      expect(document.querySelector('[data-slot="shell-announcement"]')).toBeEmptyDOMElement()
    })
  })

  it('moves focus into the page after a switch, but not on the first load', async () => {
    installFakeApi('priya')
    const { user } = renderApp({ at: '/ask' })
    await sidebarReady()
    expect(document.body).toHaveFocus()
    await switchViaMenu(user, 'Marcus')
    await waitFor(() => expect(marcusToast()).toBe(true))
    expect(screen.getByRole('main')).toHaveFocus()
  })

  it("doesn't leave the rail's failed handbook request for the Handbook page to find", async () => {
    installFakeApi('priya')
    let hits = 0
    const fail = () =>
      HttpResponse.json(
        { type: 'about:blank', title: 'Boom', status: 500, instance: '/x' },
        { status: 500 },
      )
    const handler = http.get(`${window.location.origin}/api/v1/handbook`, () => {
      hits += 1
      return fail()
    })
    server.use(handler)
    const { queryClient, router } = renderApp({ at: '/ask' })
    await screen.findByRole('complementary', { name: 'Sandbox status' })
    await waitFor(() => expect(hits).toBeGreaterThan(0))
    await waitFor(() => expect(queryClient.isFetching()).toBe(0))
    // The handbook comes back. Opening the page must ask again, not reuse the rail's failure.
    server.resetHandlers()
    installFakeApi('priya')
    installFakeHandbook('priya')
    await act(() => router.navigate('/handbook'))
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Employee handbook' }),
    ).toBeVisible()
    expect(await screen.findByRole('heading', { level: 2, name: 'Welcome' })).toBeVisible()
  })

  it('hides the rail below 760 px when it has nothing to show, and shows it once there is a figure', async () => {
    installFakeApi('priya')
    renderApp({ at: '/ask' })
    const rail = await screen.findByRole('complementary', { name: 'Sandbox status' })
    await within(rail).findByRole('region', { name: 'At a glance' })
    expect(rail).not.toHaveClass('max-[760px]:hidden')
  })
})

describe('the shell: time off, approvals, and the rail', () => {
  it('clips the sheet without a scroll container on the Time off page, so its docked form can stick', async () => {
    installFakeApi('priya')
    installFakeTimeOff()
    renderApp({ at: '/time-off' })
    await screen.findByRole('heading', { level: 3, name: 'Upcoming' })
    expect(document.querySelector('[data-slot="shell-sheet"]')).toHaveClass('overflow-clip')
  })

  it('clips the sheet when a page asks for it and not otherwise, and stops when the page is left', async () => {
    installFakeApi('priya')
    installFakeTimeOff()
    const { router } = renderApp({ at: '/ask' })
    await screen.findByRole('navigation', { name: 'Main' })
    const sheet = () => document.querySelector('[data-slot="shell-sheet"]')
    expect(sheet()).toHaveClass('overflow-hidden')
    expect(sheet()).not.toHaveClass('overflow-clip')

    act(() => useShellLayout.getState().setStickyPanel(true))
    expect(sheet()).toHaveClass('overflow-clip')
    act(() => useShellLayout.getState().setStickyPanel(false))
    expect(sheet()).toHaveClass('overflow-hidden')

    // The Time off page sets it by itself, and leaving the page clears it.
    await act(() => router.navigate('/time-off'))
    await screen.findByRole('heading', { level: 3, name: 'Upcoming' })
    expect(sheet()).toHaveClass('overflow-clip')
    await act(() => router.navigate('/ask'))
    await waitFor(() => expect(sheet()).toHaveClass('overflow-hidden'))
    expect(useShellLayout.getState().stickyPanel).toBe(false)
  })

  const navLinks = () =>
    within(screen.getByRole('navigation', { name: 'Main' }))
      .getAllByRole('link')
      .map((link) => accessibleNameOf(link))

  it('shows Marcus the Approvals item with the count in its name, and Priya none', async () => {
    installFakeApi('marcus')
    renderApp({ at: '/ask' })
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    const approvals = await within(nav).findByRole('link', { name: 'Approvals, 2 waiting' })
    expect(approvals).toHaveAttribute('href', '/approvals')
    expect(within(approvals).getByText('2')).toBeVisible()
  })

  it('shows Priya no Approvals item', async () => {
    installFakeApi('priya')
    renderApp({ at: '/ask' })
    await screen.findByRole('navigation', { name: 'Main' })
    expect(navLinks()).toEqual(['Ask', 'Time off', 'My cases', 'Directory', 'Handbook'])
  })

  it('shows plain "Approvals" with no badge when nothing is waiting', async () => {
    installFakeApi('marcus')
    installFakeTimeOff({ manager: true, waiting: [] })
    renderApp({ at: '/ask' })
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    const approvals = await within(nav).findByRole('link', { name: 'Approvals' })
    expect(within(approvals).queryByText('0')).not.toBeInTheDocument()
    expect(approvals.querySelector('[data-slot="nav-count"]')).toBeNull()
  })

  it('keeps the Approvals item, without a count, when the summary fails', async () => {
    installFakeApi('marcus')
    server.use(
      http.get(`${window.location.origin}/api/v1/time-off/summary`, () =>
        HttpResponse.json(
          { type: 'about:blank', title: 'Boom', status: 500, instance: '/x' },
          { status: 500 },
        ),
      ),
    )
    renderApp({ at: '/ask' })
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    expect(await within(nav).findByRole('link', { name: 'Approvals' })).toBeVisible()
  })

  it('removes Approvals when Marcus switches to Priya, and never shows it as Priya', async () => {
    installFakeApi('marcus')
    const { user } = renderApp({ at: '/ask' })
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    await within(nav).findByRole('link', { name: 'Approvals, 2 waiting' })

    // From the first change on, note the person the switcher names and whether Approvals shows.
    const seen: { who: string; approvals: boolean }[] = []
    const observer = new MutationObserver(() => {
      const main = document.querySelector('nav[aria-label="Main"]')
      const switcher = document.querySelector('[data-slot="persona-switcher"]')
      if (!main || !switcher) return
      seen.push({
        who: accessibleNameOf(switcher),
        approvals: main.textContent?.includes('Approvals') ?? false,
      })
    })
    observer.observe(document.body, { childList: true, subtree: true, attributes: true })
    await switchViaMenu(user, 'Priya')
    await waitFor(() => expect(personaSwitcher()).toHaveAccessibleName(PRIYA))
    await waitFor(() => expect(toast()).not.toBeNull())
    observer.disconnect()

    expect(navLinks()).toEqual(['Ask', 'Time off', 'My cases', 'Directory', 'Handbook'])
    expect(seen.filter((entry) => entry.who === PRIYA).length).toBeGreaterThan(0)
    expect(seen.filter((entry) => entry.who === PRIYA && entry.approvals)).toEqual([])
  })

  describe('HR: the Cases item and the rail', () => {
    const countsUrl = () => `${window.location.origin}/api/v1/cases/counts`
    const failCounts = () =>
      server.use(
        http.get(countsUrl(), () =>
          HttpResponse.json(
            { type: 'about:blank', title: 'Boom', status: 500, instance: '/x' },
            { status: 500 },
          ),
        ),
      )

    it('gives Dana Cases after Handbook with "3 new" in its badge and name, and no My cases', async () => {
      installFakeApi('dana')
      renderApp({ at: '/ask' })
      const nav = await screen.findByRole('navigation', { name: 'Main' })
      const cases = await within(nav).findByRole('link', { name: 'Cases, 3 new' })
      expect(cases).toHaveAttribute('href', '/cases')
      expect(cases.querySelector('[data-slot="nav-count"]')).toHaveTextContent('3 new')
      expect(navLinks()).toEqual(['Ask', 'Time off', 'Directory', 'Handbook', 'Cases, 3 new'])
    })

    it('shows plain "Cases" with no badge when nothing is new', async () => {
      installFakeApi('dana')
      server.use(http.get(countsUrl(), () => HttpResponse.json({ new: 0, replyDue: 0 })))
      renderApp({ at: '/ask' })
      const nav = await screen.findByRole('navigation', { name: 'Main' })
      const cases = await within(nav).findByRole('link', { name: 'Cases' })
      expect(cases.querySelector('[data-slot="nav-count"]')).toBeNull()
    })

    it('keeps the Cases item, without a count, when the counts fail', async () => {
      installFakeApi('dana')
      failCounts()
      renderApp({ at: '/ask' })
      const nav = await screen.findByRole('navigation', { name: 'Main' })
      const cases = await within(nav).findByRole('link', { name: 'Cases' })
      expect(cases.querySelector('[data-slot="nav-count"]')).toBeNull()
    })

    it('reads the counts for HR only', async () => {
      const asked = vi.fn<() => void>()
      installFakeApi('priya')
      server.use(
        http.get(countsUrl(), () => {
          asked()
          return HttpResponse.json({ new: 3, replyDue: 1 })
        }),
      )
      renderApp({ at: '/ask' })
      const glance = await screen.findByRole('region', { name: 'At a glance' })
      await within(glance).findByRole('link', { name: /Handbook updated/ })
      expect(asked).not.toHaveBeenCalled()
    })

    it('adds "new cases" and "reply due" to Dana\'s rail, after time off, before the handbook', async () => {
      installFakeApi('dana')
      renderApp({ at: '/ask' })
      const glance = await screen.findByRole('region', { name: 'At a glance' })
      await within(glance).findByRole('link', { name: '3 new cases. Open Cases' })
      const links = within(glance).getAllByRole('link')
      expect(links.map((link) => accessibleNameOf(link))).toEqual([
        '92 hours PTO available. Open Time off',
        '0 requests pending. Open Time off',
        '3 new cases. Open Cases',
        '1 reply due. Open Cases',
        'Sep 12 Handbook updated. Open Handbook',
      ])
      expect(links[2]).toHaveAttribute('href', '/cases')
      expect(links[3]).toHaveAttribute('href', '/cases')
      expect(links[2]!.querySelector('[data-slot="glance-marker"]')).not.toBeNull()
    })

    it('says "replies" for more than one, and shows no marker when nothing is new', async () => {
      installFakeApi('dana')
      server.use(http.get(countsUrl(), () => HttpResponse.json({ new: 0, replyDue: 2 })))
      renderApp({ at: '/ask' })
      const glance = await screen.findByRole('region', { name: 'At a glance' })
      const none = await within(glance).findByRole('link', { name: '0 new cases. Open Cases' })
      expect(none.querySelector('[data-slot="glance-marker"]')).toBeNull()
      expect(within(glance).getByRole('link', { name: '2 replies due. Open Cases' })).toBeVisible()
    })

    it('leaves the two figures out quietly when the counts fail', async () => {
      installFakeApi('dana')
      failCounts()
      renderApp({ at: '/ask' })
      const glance = await screen.findByRole('region', { name: 'At a glance' })
      await within(glance).findByRole('link', { name: /Handbook updated/ })
      expect(
        within(glance)
          .getAllByRole('link')
          .map((link) => accessibleNameOf(link)),
      ).toEqual([
        '92 hours PTO available. Open Time off',
        '0 requests pending. Open Time off',
        'Sep 12 Handbook updated. Open Handbook',
      ])
    })
  })

  it('adds PTO available and requests pending to the rail, before "Handbook updated"', async () => {
    installFakeApi('priya')
    installFakeTimeOff({ mine: [PRIYA_WAITING] })
    renderApp({ at: '/ask' })
    const rail = await screen.findByRole('complementary', { name: 'Sandbox status' })
    const glance = await within(rail).findByRole('region', { name: 'At a glance' })
    await within(glance).findByRole('link', { name: 'Sep 12 Handbook updated. Open Handbook' })
    const links = within(glance).getAllByRole('link')
    expect(links.map((link) => accessibleNameOf(link))).toEqual([
      '92 hours PTO available. Open Time off',
      '1 request pending. Open Time off',
      'Sep 12 Handbook updated. Open Handbook',
    ])
    expect(links[0]).toHaveAttribute('href', '/time-off')
    expect(links[1]).toHaveAttribute('href', '/time-off')
    // Requests pending carry the marker when some wait, as approvals waiting do; PTO never does.
    expect(links[1]!.querySelector('[data-slot="glance-marker"]')).not.toBeNull()
    expect(links[0]!.querySelector('[data-slot="glance-marker"]')).toBeNull()
    // The figure is the API's label split at its parenthesis, with no days beside it.
    expect(within(links[0]!).getByText('92 hours')).toBeVisible()
    expect(within(links[0]!).queryByText(/days/)).not.toBeInTheDocument()
  })

  it('adds "approvals waiting" for a manager, with the marker when some wait', async () => {
    installFakeApi('marcus')
    renderApp({ at: '/ask' })
    const glance = await screen.findByRole('region', { name: 'At a glance' })
    const link = await within(glance).findByRole('link', {
      name: '2 approvals waiting. Open Approvals',
    })
    expect(link).toHaveAttribute('href', '/approvals')
    expect(link.querySelector('[data-slot="glance-marker"]')).not.toBeNull()
  })

  it('shows no marker when a manager has nothing waiting, and no approvals line for anyone else', async () => {
    installFakeApi('marcus')
    installFakeTimeOff({ manager: true, waiting: [] })
    renderApp({ at: '/ask' })
    const glance = await screen.findByRole('region', { name: 'At a glance' })
    const link = await within(glance).findByRole('link', {
      name: '0 approvals waiting. Open Approvals',
    })
    expect(link.querySelector('[data-slot="glance-marker"]')).toBeNull()
  })

  it('adds no approvals line to the rail of someone who manages no one', async () => {
    installFakeApi('priya')
    renderApp({ at: '/ask' })
    const priyas = await screen.findByRole('region', { name: 'At a glance' })
    await within(priyas).findByRole('link', { name: /Handbook updated/ })
    expect(within(priyas).queryByRole('link', { name: /approvals waiting/ })).toBeNull()
  })

  it('leaves the time-off figures out when the summary fails, and keeps "Handbook updated"', async () => {
    installFakeApi('priya')
    server.use(
      http.get(`${window.location.origin}/api/v1/time-off/summary`, () =>
        HttpResponse.json(
          { type: 'about:blank', title: 'Boom', status: 500, instance: '/x' },
          { status: 500 },
        ),
      ),
    )
    renderApp({ at: '/ask' })
    const glance = await screen.findByRole('region', { name: 'At a glance' })
    expect(
      within(glance)
        .getAllByRole('link')
        .map((link) => accessibleNameOf(link)),
    ).toEqual(['Sep 12 Handbook updated. Open Handbook'])
  })
})
