import { act, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { memo, useEffect } from 'react'
import { Outlet, type RouteObject } from 'react-router'
import { describe, expect, it } from 'vitest'
import { getGetMeQueryKey, useSwitchPersona } from '@/api/generated'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { meFor } from '@/test/fixtures'
import { installFakeApi } from '@/test/fake-api'
import { apiFetch } from '@/lib/api-fetch'
import { server } from '@/test/msw'
import { signOutViaMenu, switchViaMenu } from '@/test/persona-menu'
import { renderApp } from '@/test/render-app'
import { RequireSession } from './RequireSession'
import { getSessionStatus } from './session-status'
import { signInAs, useMe } from './useMe'

function gate() {
  let resolve = () => {}
  const promise = new Promise<void>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

const heading = (name: string) => screen.findByRole('heading', { level: 1, name })
const LANDING = 'Your open-door policy, now always open.'
// The home's greeting names the person, and its first word depends on the hour.
const greetingRegex = (name: string) =>
  new RegExp(`^Good (morning|afternoon|evening), ${name.split(' ')[0]}\\.$`)
const signedInAs = (name: string) =>
  screen.findByRole('heading', { level: 1, name: greetingRegex(name) })

describe('the router', () => {
  it('sends an app route to the landing page when nobody is signed in', async () => {
    installFakeApi()
    const { router } = renderApp({ at: '/directory' })
    await heading(LANDING)
    expect(router.state.location.pathname).toBe('/')
  })

  it('sends an unknown route to the landing page for an anonymous visitor', async () => {
    installFakeApi()
    const { router } = renderApp({ at: '/nowhere' })
    await heading(LANDING)
    expect(router.state.location.pathname).toBe('/')
  })

  it('shows the plain error, outside the shell, when the first /me fails with a 500', async () => {
    const api = installFakeApi('priya')
    api.failMe(500)
    renderApp({ at: '/ask' })
    await heading('Something went wrong on our side.')
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('retries the failed /me when Retry is pressed', async () => {
    const api = installFakeApi('priya')
    api.failMe(500)
    const { user } = renderApp({ at: '/ask' })
    await heading('Something went wrong on our side.')
    api.failMe(null)
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await signedInAs('Priya Raman')).toBeInTheDocument()
  })

  it('shows "This sandbox has reset." when a later request is a 401', async () => {
    const api = installFakeApi('priya')
    const { queryClient } = renderApp({ at: '/ask' })
    await signedInAs('Priya Raman')
    api.expire()
    await act(() => queryClient.invalidateQueries())
    await heading('This sandbox has reset.')
    expect(
      screen.queryByRole('heading', { level: 1, name: /^Good (morning|afternoon|evening),/ }),
    ).not.toBeInTheDocument()
  })

  it('does not call a sandbox reset when a read is 401 because another tab switched person', async () => {
    const api = installFakeApi('priya')
    const { queryClient } = renderApp({ at: '/ask' })
    await signedInAs('Priya Raman')
    // Another tab switched to Marcus, which rotated the cookie, so this tab's next read is a 401
    // while /me (with the new cookie) names Marcus.
    api.signIn('marcus')
    server.use(
      http.get(`${window.location.origin}/api/v1/other-read`, () =>
        HttpResponse.json(
          { type: 'about:blank', title: 'Not signed in', status: 401, instance: '/x' },
          { status: 401 },
        ),
      ),
    )
    await act(() =>
      queryClient
        .fetchQuery({ queryKey: ['other-read'], queryFn: () => apiFetch('/api/v1/other-read') })
        .catch(() => undefined),
    )
    await signedInAs('Marcus Bell')
    expect(screen.queryByText('This sandbox has reset.')).not.toBeInTheDocument()
  })

  it('shows the reset page when a read is 401 and /me is 401 too, as after a sign-out elsewhere', async () => {
    const api = installFakeApi('priya')
    const { queryClient } = renderApp({ at: '/ask' })
    await signedInAs('Priya Raman')
    api.expire()
    server.use(
      http.get(`${window.location.origin}/api/v1/other-read`, () =>
        HttpResponse.json(
          { type: 'about:blank', title: 'Not signed in', status: 401, instance: '/x' },
          { status: 401 },
        ),
      ),
    )
    await act(() =>
      queryClient
        .fetchQuery({ queryKey: ['other-read'], queryFn: () => apiFetch('/api/v1/other-read') })
        .catch(() => undefined),
    )
    expect(await heading('This sandbox has reset.')).toBeInTheDocument()
  })

  it('does not call a sandbox reset when a read is 401 but /me still names the same person', async () => {
    installFakeApi('priya')
    const { queryClient } = renderApp({ at: '/ask' })
    await signedInAs('Priya Raman')
    server.use(
      http.get(`${window.location.origin}/api/v1/other-read`, () =>
        HttpResponse.json(
          { type: 'about:blank', title: 'Not signed in', status: 401, instance: '/x' },
          { status: 401 },
        ),
      ),
    )
    await act(() =>
      queryClient
        .fetchQuery({ queryKey: ['other-read'], queryFn: () => apiFetch('/api/v1/other-read') })
        .catch(() => undefined),
    )
    await act(() => new Promise((resolve) => setTimeout(resolve, 50)))
    expect(screen.queryByText('This sandbox has reset.')).not.toBeInTheDocument()
    await signedInAs('Priya Raman')
  })

  it('sends the reset page button to a landing page that does not find the old person', async () => {
    const api = installFakeApi('priya')
    const { queryClient, user, router } = renderApp({ at: '/ask' })
    await signedInAs('Priya Raman')
    api.expire()
    await act(() => queryClient.invalidateQueries())
    await user.click(await screen.findByRole('button', { name: 'Choose who to be' }))
    await heading(LANDING)
    expect(router.state.location.pathname).toBe('/')
  })

  it('shows nothing but a screen-reader status while the first /me loads', async () => {
    installFakeApi('priya')
    const hold = gate()
    server.use(
      http.get(`${window.location.origin}/api/v1/me`, async () => {
        await hold.promise
        return HttpResponse.json(meFor('priya'))
      }),
    )
    renderApp({ at: '/ask' })
    expect(await screen.findByText('Loading…')).toHaveClass('sr-only')
    hold.resolve()
    await signedInAs('Priya Raman')
  })

  it('redirects a signed-in visitor at / to /ask', async () => {
    installFakeApi('priya')
    const { router } = renderApp({ at: '/' })
    await signedInAs('Priya Raman')
    expect(router.state.location.pathname).toBe('/ask')
  })

  it('shows not found inside the session for an unknown route', async () => {
    installFakeApi('priya')
    renderApp({ at: '/nowhere' })
    expect(await heading("We couldn't find that page.")).toBeInTheDocument()
  })

  it('starts a sandbox as the chosen person', async () => {
    const api = installFakeApi()
    const { user, router } = renderApp({ at: '/' })
    await user.click(await screen.findByRole('button', { name: /^Marcus / }))
    await signedInAs('Marcus Bell')
    expect(router.state.location.pathname).toBe('/ask')
    expect(api.signedInAs()).toBe('marcus')
  })

  it('switches to another person', async () => {
    installFakeApi('priya')
    const { user } = renderApp({ at: '/ask' })
    await signedInAs('Priya Raman')
    await switchViaMenu(user, 'Marcus')
    await signedInAs('Marcus Bell')
    expect(
      screen.queryByRole('heading', { level: 1, name: greetingRegex('Priya Raman') }),
    ).not.toBeInTheDocument()
  })

  it('does not show the reset page when an anonymous 401 is followed by a sign-in elsewhere', async () => {
    const api = installFakeApi()
    const { queryClient, router } = renderApp({ at: '/' })
    await heading(LANDING)
    api.signIn('priya')
    await act(() => queryClient.invalidateQueries())
    await signedInAs('Priya Raman')
    expect(router.state.location.pathname).toBe('/ask')
    expect(screen.queryByText('This sandbox has reset.')).not.toBeInTheDocument()
  })

  it('ignores a 401 from a switch that started before the identity changed', async () => {
    const api = installFakeApi('priya')
    // The first switch succeeds; the second, sent before that, is answered 401 afterward, as the
    // real server does once the first has rotated the session.
    const gates = [gate(), gate()]
    let calls = 0
    server.use(
      http.put(`${window.location.origin}/api/v1/session/persona`, async () => {
        const call = calls++
        await gates[call]!.promise
        if (call === 0) api.signIn('marcus')
        return call === 0
          ? HttpResponse.json(meFor('marcus'))
          : HttpResponse.json(
              { type: 'about:blank', title: 'Not signed in', status: 401, instance: '/x' },
              { status: 401 },
            )
      }),
    )
    // The real shell's switcher refuses a second switch while one runs, so two overlapping
    // switches (as from two tabs) are started from the test shell's own button.
    const { user } = renderApp({ at: '/ask', routes: shellRoutes })
    await waitFor(() => expect(screen.getByTestId('header')).toHaveTextContent('Priya Raman'))
    await user.click(screen.getByRole('button', { name: 'Switch' }))
    await user.click(screen.getByRole('button', { name: 'Switch' }))
    gates[0]!.resolve()
    await waitFor(() => expect(screen.getByTestId('header')).toHaveTextContent('Marcus Bell'))
    gates[1]!.resolve()
    await act(() => new Promise((resolve) => setTimeout(resolve, 50)))
    expect(screen.queryByText('This sandbox has reset.')).not.toBeInTheDocument()
    expect(screen.getByTestId('header')).toHaveTextContent('Marcus Bell')
  })

  it('signs out to the landing page, and a later visit finds nobody', async () => {
    const api = installFakeApi('priya')
    const { user, router } = renderApp({ at: '/ask' })
    await signedInAs('Priya Raman')
    await signOutViaMenu(user)
    await heading(LANDING)
    expect(router.state.location.pathname).toBe('/')
    expect(api.signedInAs()).toBeNull()
    await act(() => router.navigate('/ask'))
    await heading(LANDING)
  })
})

// A header-like component that would stay mounted for the whole signed-in session. It is not a
// page: it sits beside the outlet, as the future shell will. It is memoized, so nothing re-renders
// it from above: only the remount that the reset count forces can replace its data.
const rendered: string[] = []
const Header = memo(function Header() {
  const me = useMe()
  const name = me.data ? `${me.data.givenName} ${me.data.familyName}` : null
  useEffect(() => {
    if (name) rendered.push(name)
  })
  return (
    <header data-testid="header" data-fetch={me.fetchStatus}>
      {name ?? 'loading'}
    </header>
  )
})

function SwitchToMarcus() {
  const queryClient = useQueryClient()
  const mutation = useSwitchPersona({ mutation: { onSuccess: (me) => signInAs(queryClient, me) } })
  return (
    <button type="button" onClick={() => mutation.mutate({ data: { persona: 'marcus' } })}>
      Switch
    </button>
  )
}

// A page's own query, standing in for the directory: its data belongs to whoever fetched it.
let peopleFetches = 0
const peopleRendered: number[] = []
function People() {
  const people = useQuery({ queryKey: ['people'], queryFn: async () => (peopleFetches += 1) })
  useEffect(() => {
    if (people.data !== undefined) peopleRendered.push(people.data)
  })
  return <p data-testid="people">{people.data === undefined ? 'none' : `era ${people.data}`}</p>
}

function Shell() {
  return (
    <>
      <Header />
      <People />
      <SwitchToMarcus />
      <Outlet />
    </>
  )
}

const shellRoutes: RouteObject[] = [
  {
    element: <RequireSession />,
    children: [{ element: <Shell />, children: [{ path: '/ask', element: <p>page</p> }] }],
  },
]

describe('the identity reset', () => {
  it('never renders the old person after a switch, even in what sits beside the outlet', async () => {
    installFakeApi('priya')
    rendered.length = 0
    const { user } = renderApp({ at: '/ask', routes: shellRoutes })
    await waitFor(() => expect(screen.getByTestId('header')).toHaveTextContent('Priya Raman'))
    await waitFor(() => expect(screen.getByTestId('header')).toHaveAttribute('data-fetch', 'idle'))
    const before = rendered.length

    await user.click(screen.getByRole('button', { name: 'Switch' }))
    await waitFor(() => expect(screen.getByTestId('header')).toHaveTextContent('Marcus Bell'))

    // Every render of the header after the switch was Marcus, none was Priya.
    expect(rendered.slice(before)).not.toContain('Priya Raman')
    expect(rendered.at(-1)).toBe('Marcus Bell')
  })
})

describe('a change of person in another tab', () => {
  it('resets this tab when /me answers with someone else', async () => {
    const api = installFakeApi('priya')
    rendered.length = 0
    peopleFetches = 0
    peopleRendered.length = 0
    const { queryClient } = renderApp({ at: '/ask', routes: shellRoutes })
    await waitFor(() => expect(screen.getByTestId('header')).toHaveTextContent('Priya Raman'))
    await waitFor(() => expect(screen.getByTestId('people')).toHaveTextContent('era 1'))
    const countBefore = getSessionStatus().resetCount
    const headerBefore = rendered.length
    const peopleBefore = peopleRendered.length

    // Another tab switches to Marcus. This tab finds out when /me is refetched on focus.
    api.signIn('marcus')
    await act(() => queryClient.invalidateQueries({ queryKey: getGetMeQueryKey() }))

    await waitFor(() => expect(screen.getByTestId('header')).toHaveTextContent('Marcus Bell'))
    await waitFor(() => expect(screen.getByTestId('people')).toHaveTextContent('era 2'))
    expect(getSessionStatus().resetCount).toBeGreaterThan(countBefore)
    expect(rendered.slice(headerBefore)).not.toContain('Priya Raman')
    expect(peopleRendered.slice(peopleBefore)).not.toContain(1)
  })
})
