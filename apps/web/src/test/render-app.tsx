import { QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider, type RouteObject } from 'react-router'
import { vi } from 'vitest'
import { routes as appRoutes } from '@/app/router'
import { markExpired, resetSessionStatus } from '@/app/session-status'
import { createQueryClient } from '@/lib/query-client'

// Node's fetch needs an absolute URL; the app passes a path such as "/api/v1/me".
function stubAbsoluteUrls() {
  const realFetch = globalThis.fetch
  vi.stubGlobal('fetch', (input: RequestInfo | URL, init?: RequestInit) =>
    realFetch(typeof input === 'string' ? `${window.location.origin}${input}` : input, init),
  )
}

interface RenderAppOptions {
  /** The first URL. Defaults to the landing page. */
  at?: string
  /** Replaces the app's routes, to put a test component under the real session guard. */
  routes?: RouteObject[]
}

/** The app in a memory router, with a fresh QueryClient that follows the production rules. */
export function renderApp({ at = '/', routes = appRoutes }: RenderAppOptions = {}) {
  stubAbsoluteUrls()
  // The session status is module state, shared by every test in the file.
  resetSessionStatus()
  const queryClient = createQueryClient({ onUnauthorized: markExpired, retryDelayMs: 0 })
  const router = createMemoryRouter(routes, { initialEntries: [at] })
  const user = userEvent.setup()
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { queryClient, router, user }
}
