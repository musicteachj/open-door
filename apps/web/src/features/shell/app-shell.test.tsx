import { act, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getGetMeQueryKey } from '@/api/generated'
import { getSessionStatus } from '@/app/session-status'
import { useChatStore } from '@/features/chat/store'
import { installFakeApi } from '@/test/fake-api'
import { meFor } from '@/test/fixtures'
import { useShellToast } from './toast-store'
import { personaSwitcher, signOutViaMenu, switchViaMenu } from '@/test/persona-menu'
import { server } from '@/test/msw'
import { renderApp } from '@/test/render-app'

const SWITCH = () => `${window.location.origin}/api/v1/session/persona`
const END = () => `${window.location.origin}/api/v1/session`
const LANDING = 'Your open-door policy, now always open.'
const PRIYA = 'Switch persona. Current: Priya Raman, Visual Merchandiser'
const MARCUS = 'Switch persona. Current: Marcus Bell, Store Manager'

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
    ).toEqual(['Ask', 'Directory'])
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

  it('puts the rail below the content on a narrow screen, and leaves the glance list empty', async () => {
    installFakeApi('priya')
    renderApp({ at: '/ask' })
    const rail = await screen.findByRole('complementary', { name: 'Sandbox status' })
    expect(rail.parentElement).toHaveClass('max-[760px]:grid-cols-1')
    expect(within(rail).queryByRole('region', { name: 'At a glance' })).not.toBeInTheDocument()
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
    expect(toast()).toHaveTextContent('Now viewing as Marcus Bell.')
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
    await user.click(await screen.findByRole('button', { name: /^Start a sandbox as Priya / }))
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
    expect(within(sidebar).getByRole('button', { name: /^Switch persona/ })).toBeInTheDocument()
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
        'Switch persona. Current: Dana Whitfield, HR Business Partner',
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
    await user.click(await screen.findByRole('button', { name: /^Start a sandbox as Priya / }))
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

  it('hides the rail below 760 px when it has nothing to show', async () => {
    installFakeApi('priya')
    renderApp({ at: '/ask' })
    const rail = await screen.findByRole('complementary', { name: 'Sandbox status' })
    expect(rail).toHaveClass('max-[760px]:hidden')
  })
})
