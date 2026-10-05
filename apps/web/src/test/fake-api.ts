import { http, HttpResponse } from 'msw'
import type { PersonaKey, SandboxCreated } from '@/api/generated'
import { meFor } from './fixtures'
import { server } from './msw'

// A fake API that remembers who is signed in, so starting a sandbox, switching persona, and
// signing out change what GET /me returns, as the real server does.
const url = (path: string) => `${window.location.origin}${path}`

function problem(status: number, title: string) {
  return HttpResponse.json(
    { type: 'about:blank', title, status, instance: '/api/v1/me' },
    { status, headers: { 'X-Request-ID': 'a'.repeat(32) } },
  )
}

export function installFakeApi(initial: PersonaKey | null = null) {
  let current: PersonaKey | null = initial
  let meFailure: number | null = null

  server.use(
    http.get(url('/api/v1/me'), () => {
      if (meFailure !== null) return problem(meFailure, 'Failure')
      return current === null ? problem(401, 'Not signed in') : HttpResponse.json(meFor(current))
    }),
    http.post(url('/api/v1/sandboxes'), async ({ request }) => {
      const body = (await request.json()) as { persona?: PersonaKey } | null
      current = body?.persona ?? 'priya'
      const created: SandboxCreated = {
        tenant: { id: 'tenant-1', expiresAt: '2026-10-06T12:00:00Z' },
        me: meFor(current),
      }
      return HttpResponse.json(created, { status: 201 })
    }),
    http.put(url('/api/v1/session/persona'), async ({ request }) => {
      if (current === null) return problem(401, 'Not signed in')
      current = ((await request.json()) as { persona: PersonaKey }).persona
      return HttpResponse.json(meFor(current))
    }),
    http.delete(url('/api/v1/session'), () => {
      current = null
      return new HttpResponse(null, { status: 204 })
    }),
  )

  return {
    /** Who the fake thinks is signed in. */
    signedInAs: () => current,
    /** Someone signs in elsewhere, such as another tab, without this page knowing. */
    signIn: (persona: PersonaKey) => {
      current = persona
    },
    /** The sandbox's 24 hours are up: every later request is a 401. */
    expire: () => {
      current = null
    },
    /** Make GET /me answer this status, or work again with null. */
    failMe: (status: number | null) => {
      meFailure = status
    },
  }
}
