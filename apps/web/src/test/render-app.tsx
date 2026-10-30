import { QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode } from 'react'
import { createMemoryRouter, RouterProvider, type RouteObject } from 'react-router'
import { routes as appRoutes } from '@/app/router'
import { markExpired, resetSessionStatus } from '@/app/session-status'
import { createQueryClient } from '@/lib/query-client'
import { stubAbsoluteUrls } from './absolute-urls'

interface RenderAppOptions {
  /** The first URL. Defaults to the landing page. */
  at?: string
  /** Replaces the app's routes, to put a test component under the real session guard. */
  routes?: RouteObject[]
  /** Wraps the app in React's StrictMode, which runs every effect twice in development. */
  strict?: boolean
}

/** The app in a memory router, with a fresh QueryClient that follows the production rules. */
export function renderApp({ at = '/', routes = appRoutes, strict = false }: RenderAppOptions = {}) {
  stubAbsoluteUrls()
  // The session status is module state, shared by every test in the file.
  resetSessionStatus()
  const queryClient = createQueryClient({ onUnauthorized: markExpired, retryDelayMs: 0 })
  const router = createMemoryRouter(routes, { initialEntries: [at] })
  const user = userEvent.setup()
  const app = (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
  render(strict ? <StrictMode>{app}</StrictMode> : app)
  return { queryClient, router, user }
}
