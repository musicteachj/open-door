import { http, HttpResponse } from 'msw'
import type { PersonaKey, SandboxCreated } from '@/api/generated'
import { handbookOverview } from './fake-handbook'
import { NO_BUDGET_STOP, TEXTS } from './fake-assistant'
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
  // When the sandbox resets, or null for the fixtures' default (21.5 hours from now).
  let expiresAt: string | null = null
  const me = (persona: PersonaKey) => meFor(persona, expiresAt ?? undefined)

  server.use(
    http.get(url('/api/v1/me'), () => {
      if (meFailure !== null) return problem(meFailure, 'Failure')
      return current === null ? problem(401, 'Not signed in') : HttpResponse.json(me(current))
    }),
    // The assistant home's "Handbook updated" figure reads the handbook's version, so every
    // signed-in test has an answer. A test that installs the fake handbook overrides it.
    http.get(url('/api/v1/handbook'), () =>
      HttpResponse.json(handbookOverview(current === 'mateo' ? 'mateo' : 'priya')),
    ),
    // The shell reads the time-off summary for the Approvals count and the rail's figures, so every
    // signed-in test has an answer: Marcus has two waiting, nobody else has any. A test that
    // installs the fake time-off routes (fake-time-off.ts) overrides it.
    http.get(url('/api/v1/time-off/summary'), () =>
      HttpResponse.json({
        ptoAvailableMinutes: 5520,
        ptoAvailableLabel: '92 hours (11.5 days)',
        pendingCount: 0,
        approver: { name: 'Marcus Bell' },
        waitingCount: current === 'marcus' ? 2 : null,
      }),
    ),
    // The assistant page reads these two on arrival: nothing asked yet, and the fixed texts. A test
    // that needs a conversation or a stream installs its own (fake-assistant.ts), which wins.
    http.get(url('/api/v1/assistant/texts'), () => HttpResponse.json(TEXTS)),
    http.get(url('/api/v1/assistant/conversations/current'), () => HttpResponse.json(null)),
    http.get(url('/api/v1/assistant/budget'), () => HttpResponse.json(NO_BUDGET_STOP)),
    http.post(url('/api/v1/sandboxes'), async ({ request }) => {
      const body = (await request.json()) as { persona?: PersonaKey } | null
      current = body?.persona ?? 'priya'
      const created: SandboxCreated = {
        tenant: { id: 'tenant-1', expiresAt: expiresAt ?? '2026-10-06T12:00:00Z' },
        me: me(current),
      }
      return HttpResponse.json(created, { status: 201 })
    }),
    http.put(url('/api/v1/session/persona'), async ({ request }) => {
      if (current === null) return problem(401, 'Not signed in')
      current = ((await request.json()) as { persona: PersonaKey }).persona
      return HttpResponse.json(me(current))
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
    /** When the sandbox resets, as /me and the start and switch answers report it. */
    setExpiry: (iso: string) => {
      expiresAt = iso
    },
    /** Make GET /me answer this status, or work again with null. */
    failMe: (status: number | null) => {
      meFailure = status
    },
  }
}
