import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { stubAbsoluteUrls } from '@/test/absolute-urls'
import { meFor } from '@/test/fixtures'
import { server } from '@/test/msw'
import { DUMMY_TURNSTILE_TOKEN, turnstileFake } from '@/test/turnstile'
import { useIdentityBusy } from './useIdentityBusy'
import { useStartSandbox } from './useStartSandbox'

const url = (path: string) => `${window.location.origin}${path}`

function setup() {
  stubAbsoluteUrls()
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
  return renderHook(() => ({ start: useStartSandbox(), gate: useIdentityBusy() }), { wrapper })
}

const slot = () => document.body.appendChild(document.createElement('div'))

describe('useStartSandbox', () => {
  it('is pending, and the shared identity gate is busy, while the token is awaited', async () => {
    let release: () => void = () => {}
    turnstileFake.hold = new Promise<void>((resolve) => {
      release = resolve
    })
    server.use(http.post(url('/api/v1/sandboxes'), () => HttpResponse.json(sandboxFor('priya'))))
    const { result } = setup()
    act(() => result.current.start.mutate({ data: { persona: 'priya' } }, slot()))

    await waitFor(() => expect(result.current.start.isPending).toBe(true))
    expect(result.current.gate.starting).toBe(true)
    expect(result.current.gate.busy).toBe(true)
    expect(result.current.start.variables?.data.persona).toBe('priya')
    // The mutation cache keeps `variables`: plain data only, never the slot's DOM element.
    expect(result.current.start.variables).toEqual({ data: { persona: 'priya' } })
    expect(Object.keys(result.current.start.variables ?? {})).toEqual(['data'])

    release()
    await waitFor(() => expect(result.current.start.isPending).toBe(false))
    expect(result.current.gate.busy).toBe(false)
  })

  it('shows a refusal instead of swallowing it', async () => {
    server.use(
      http.post(url('/api/v1/sandboxes'), () =>
        HttpResponse.json(
          { type: 'sandbox-start-limit', title: 'Refused', status: 429, detail: 'Wait.' },
          { status: 429, headers: { 'Content-Type': 'application/problem+json' } },
        ),
      ),
    )
    const { result } = setup()
    act(() => result.current.start.mutate({ data: { persona: 'priya' } }, slot()))
    await waitFor(() => expect(result.current.start.isError).toBe(true))
    expect(result.current.start.error).toBeTruthy()
  })

  it('sends the empty token, and renders nowhere, when there is no slot', async () => {
    let sent: unknown
    server.use(
      http.post(url('/api/v1/sandboxes'), async ({ request }) => {
        sent = await request.json()
        return HttpResponse.json(
          { type: 'turnstile-failed', title: 'No', status: 403, detail: 'Could not confirm.' },
          { status: 403, headers: { 'Content-Type': 'application/problem+json' } },
        )
      }),
    )
    const { result } = setup()
    const before = document.body.children.length
    act(() => result.current.start.mutate({ data: { persona: 'priya' } }, null))
    await waitFor(() => expect(result.current.start.isError).toBe(true))
    expect(sent).toMatchObject({ persona: 'priya', turnstileToken: '' })
    expect(turnstileFake.containers).toHaveLength(0)
    expect(document.body.children).toHaveLength(before)
  })

  it('sends the token the widget produced, rendered in the slot it was given', async () => {
    let sent: unknown
    server.use(
      http.post(url('/api/v1/sandboxes'), async ({ request }) => {
        sent = await request.json()
        return HttpResponse.json(sandboxFor('priya'))
      }),
    )
    const { result } = setup()
    const element = slot()
    act(() => result.current.start.mutate({ data: { persona: 'priya' } }, element))
    await waitFor(() => expect(result.current.start.isSuccess).toBe(true))
    expect(sent).toMatchObject({ turnstileToken: DUMMY_TURNSTILE_TOKEN })
    expect(turnstileFake.containers).toEqual([element])
  })
})

function sandboxFor(persona: 'priya') {
  return { tenant: { id: 't', expiresAt: '2026-10-06T12:00:00Z' }, me: meFor(persona) }
}
