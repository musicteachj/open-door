import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse, type JsonBodyType } from 'msw'
import type { ReactNode } from 'react'
import { MemoryRouter, useLocation } from 'react-router'
import { beforeEach, describe, expect, it } from 'vitest'
import { useStartSandbox } from '@/app/useStartSandbox'
import { stubAbsoluteUrls } from '@/test/absolute-urls'
import { meFor } from '@/test/fixtures'
import { server } from '@/test/msw'
import { turnstileFake } from '@/test/turnstile'
import { resetIdentity } from '@/lib/identity'
import { useTourStore } from '@/features/tour/store'
import { useIdentityActions } from './use-identity-actions'

const url = (path: string) => `${window.location.origin}${path}`

function setup() {
  stubAbsoluteUrls()
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
  return {
    queryClient,
    ...renderHook(
      () => ({
        actions: useIdentityActions(),
        start: useStartSandbox({ tour: true }),
        path: useLocation().pathname,
      }),
      { wrapper },
    ),
  }
}

const failSwitch = () =>
  server.use(
    http.put(url('/api/v1/session/persona'), () =>
      HttpResponse.json(
        { type: 'about:blank', title: 'Down', status: 500, instance: '/' },
        { status: 500 },
      ),
    ),
  )

beforeEach(() => {
  useTourStore.setState(useTourStore.getInitialState())
  useTourStore.getState().begin()
  useTourStore.getState().goTo(5)
})

describe('the identity gate at call time', () => {
  it('refuses a second identity action started in the same tick', () => {
    const { result, queryClient } = setup()
    let results: unknown[] = []
    act(() => {
      results = [result.current.actions.switchTo('marcus'), result.current.actions.switchTo('dana')]
      result.current.start.mutate({ data: { persona: 'priya' } }, null)
    })
    expect(results).toEqual([true, false])
    expect(queryClient.isMutating()).toBe(1)
  })
})

describe('the identity gate while a start waits for its token', () => {
  it('refuses a persona switch until the token has come and the start has finished', async () => {
    let release: () => void = () => {}
    turnstileFake.hold = new Promise<void>((resolve) => {
      release = resolve
    })
    server.use(http.put(url('/api/v1/session/persona'), () => HttpResponse.json(meFor('marcus'))))
    const { result } = setup()
    act(() =>
      result.current.start.mutate({ data: { persona: 'priya' } }, document.createElement('div')),
    )
    let started: boolean | undefined
    act(() => {
      started = result.current.actions.switchTo('marcus')
    })
    expect(started).toBe(false)
    release()
    await waitFor(() => expect(result.current.start.isPending).toBe(false))
  })
})

describe('where a switch lands', () => {
  it('goes to /ask by default, and to the page it was given otherwise', async () => {
    server.use(http.put(url('/api/v1/session/persona'), () => HttpResponse.json(meFor('marcus'))))
    const { result } = setup()
    act(() => result.current.actions.switchTo('marcus', { tour: true }))
    await waitFor(() => expect(result.current.path).toBe('/ask'))
    act(() => result.current.actions.switchTo('marcus', { tour: true, to: '/cases' }))
    await waitFor(() => expect(result.current.path).toBe('/cases'))
  })
})

describe('where a failed switch retries to', () => {
  it('lands on /ask when a failed tour switch is retried, not on the tour page', async () => {
    failSwitch()
    const { result } = setup()
    act(() => result.current.actions.switchTo('marcus', { tour: true, to: '/cases' }))
    await waitFor(() => expect(result.current.actions.failure).not.toBeNull())
    server.use(http.put(url('/api/v1/session/persona'), () => HttpResponse.json(meFor('marcus'))))
    act(() => result.current.actions.failure!.again())
    await waitFor(() => expect(result.current.path).toBe('/ask'))
  })

  it('reports whether a sign out started', () => {
    const { result } = setup()
    const results: boolean[] = []
    act(() => {
      results.push(result.current.actions.signOut())
      results.push(result.current.actions.signOut())
    })
    expect(results).toEqual([true, false])
  })
})

describe('the tour through a persona switch', () => {
  it('clears the tour at the next reset when the switch failed', async () => {
    failSwitch()
    const { result, queryClient } = setup()
    act(() => result.current.actions.switchTo('marcus', { tour: true }))
    await waitFor(() => expect(result.current.actions.failure).not.toBeNull())
    resetIdentity(queryClient)
    expect(useTourStore.getState().started).toBe(false)
  })

  it('spares the tour again when a failed switch is tried again and works', async () => {
    failSwitch()
    const { result } = setup()
    act(() => result.current.actions.switchTo('marcus', { tour: true }))
    await waitFor(() => expect(result.current.actions.failure).not.toBeNull())
    server.use(http.put(url('/api/v1/session/persona'), () => HttpResponse.json(meFor('marcus'))))
    act(() => result.current.actions.failure!.again())
    await waitFor(() => expect(result.current.actions.failure).toBeNull())
    await waitFor(() => expect(result.current.actions.busyLabel).toBeUndefined())
    expect(useTourStore.getState()).toMatchObject({ started: true, step: 5 })
  })
})

const holdRoute = (path: string, body: JsonBodyType, method: 'put' | 'post' | 'delete' = 'put') => {
  let release = () => {}
  const held = new Promise<void>((resolve) => (release = resolve))
  const seen: string[] = []
  server.use(
    http[method](url(path), async () => {
      seen.push(path)
      await held
      if (method === 'delete') return new HttpResponse(null, { status: 204 })
      return HttpResponse.json(body, { status: method === 'post' ? 201 : 200 })
    }),
  )
  return { release, seen }
}

describe('a switch, a sign out, and a sandbox start never overlap', () => {
  it('refuses to start a sandbox while a persona switch is in flight', async () => {
    const sw = holdRoute('/api/v1/session/persona', meFor('marcus'))
    const created = holdRoute(
      '/api/v1/sandboxes',
      { tenant: { id: 't', expiresAt: '2026-10-06T12:00:00Z' }, me: meFor('priya') },
      'post',
    )
    const { result } = setup()
    act(() => result.current.actions.switchTo('marcus', { tour: true }))
    await waitFor(() => expect(result.current.actions.busyLabel).toBeDefined())
    act(() => result.current.start.mutate({ data: { persona: 'priya' } }, null))
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(created.seen).toEqual([])
    expect(result.current.start.isPending).toBe(false)
    sw.release()
    await waitFor(() => expect(result.current.actions.busyLabel).toBeUndefined())
    expect(useTourStore.getState()).toMatchObject({ started: true, step: 5 })
  })

  it('refuses to switch persona while a sandbox start is in flight, and says so', async () => {
    const sw = holdRoute('/api/v1/session/persona', meFor('marcus'))
    const created = holdRoute(
      '/api/v1/sandboxes',
      { tenant: { id: 't', expiresAt: '2026-10-06T12:00:00Z' }, me: meFor('priya') },
      'post',
    )
    const { result } = setup()
    act(() => result.current.start.mutate({ data: { persona: 'priya' } }, null))
    await waitFor(() => expect(created.seen).toHaveLength(1))
    await waitFor(() => expect(result.current.actions.busyLabel).toBe('Starting a new sandbox…'))
    act(() => result.current.actions.switchTo('marcus'))
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(sw.seen).toEqual([])
    expect(useTourStore.getState().active).toBe(true)
    created.release()
  })

  it('refuses to sign out while a sandbox start is in flight', async () => {
    const out = holdRoute('/api/v1/session', null, 'delete')
    const created = holdRoute(
      '/api/v1/sandboxes',
      { tenant: { id: 't', expiresAt: '2026-10-06T12:00:00Z' }, me: meFor('priya') },
      'post',
    )
    const { result } = setup()
    act(() => result.current.start.mutate({ data: { persona: 'priya' } }, null))
    await waitFor(() => expect(created.seen).toHaveLength(1))
    await waitFor(() => expect(result.current.actions.busyLabel).toBe('Starting a new sandbox…'))
    act(() => result.current.actions.signOut())
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(out.seen).toEqual([])
    created.release()
  })

  it('refuses to sign out while a persona switch is in flight, and the reverse', async () => {
    const sw = holdRoute('/api/v1/session/persona', meFor('marcus'))
    const out = holdRoute('/api/v1/session', null, 'delete')
    const { result } = setup()
    act(() => result.current.actions.switchTo('marcus', { tour: true }))
    await waitFor(() => expect(sw.seen).toHaveLength(1))
    await waitFor(() => expect(result.current.actions.busyLabel).toBeDefined())
    act(() => result.current.actions.signOut())
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(out.seen).toEqual([])
    sw.release()
    await waitFor(() => expect(result.current.actions.busyLabel).toBeUndefined())
  })

  it('refuses to start a sandbox while a sign out is in flight', async () => {
    const out = holdRoute('/api/v1/session', null, 'delete')
    const created = holdRoute(
      '/api/v1/sandboxes',
      { tenant: { id: 't', expiresAt: '2026-10-06T12:00:00Z' }, me: meFor('priya') },
      'post',
    )
    const { result } = setup()
    act(() => result.current.actions.signOut())
    await waitFor(() => expect(out.seen).toHaveLength(1))
    await waitFor(() => expect(result.current.actions.busyLabel).toBe('Signing out…'))
    await expect(
      result.current.start.mutateAsync({ data: { persona: 'priya' } }, null),
    ).rejects.toThrow('identity change')
    act(() => result.current.start.mutate({ data: { persona: 'priya' } }, null))
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(created.seen).toEqual([])
    out.release()
  })
})
