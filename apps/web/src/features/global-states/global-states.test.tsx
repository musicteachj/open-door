import { useQuery } from '@tanstack/react-query'
import { act, screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { type RouteObject } from 'react-router'
import { describe, expect, it } from 'vitest'
import { routes } from '@/app/router'
import { RequireSession } from '@/app/RequireSession'
import { apiFetch } from '@/lib/api-fetch'
import { installFakeApi } from '@/test/fake-api'
import { server } from '@/test/msw'
import { renderApp } from '@/test/render-app'
import { isNotFound } from './errors'
import { NotFound } from './pages'
import { RouteError } from './route-error'

const REQUEST_ID = '0123456789abcdef0123456789abcdef'
const BOOM = () => `${window.location.origin}/api/v1/boom`
const heading = (name: string) => screen.findByRole('heading', { level: 1, name })

function failBoom(status: number, requestId: string | null = REQUEST_ID) {
  server.use(
    http.get(BOOM(), () =>
      HttpResponse.json(
        { type: 'about:blank', title: 'Boom', status, instance: '/api/v1/boom' },
        { status, headers: requestId ? { 'X-Request-ID': requestId } : {} },
      ),
    ),
  )
}

// A page that reads from the API and lets a failure reach the route's error boundary, as the
// directory and profile will in Stage 6.
function Page() {
  const boom = useQuery({
    queryKey: ['boom'],
    queryFn: () => apiFetch<{ text: string }>('/api/v1/boom'),
    throwOnError: true,
  })
  return <p>{boom.data?.text}</p>
}

const pageRoutes: RouteObject[] = [
  {
    element: <RequireSession />,
    children: [
      {
        errorElement: <RouteError />,
        children: [
          { path: '/ask', element: <Page /> },
          { path: '*', element: <NotFound /> },
        ],
      },
    ],
  },
]

describe('the session-expired page', () => {
  it('shows outside the shell after a 401 while signed in, with its title focused', async () => {
    const api = installFakeApi('priya')
    const { queryClient } = renderApp({ at: '/ask', routes: pageRoutes })
    server.use(http.get(BOOM(), () => HttpResponse.json({ text: 'fine' })))
    await screen.findByText('fine')
    api.expire()
    await act(() => queryClient.invalidateQueries())
    const title = await heading('This sandbox has reset.')
    expect(title).toHaveFocus()
    expect(
      screen.getByText('Sandboxes last 24 hours. Start a new one to keep exploring.'),
    ).toBeInTheDocument()
    // Outside the shell: the logo is there, and no navigation is.
    expect(screen.getByText('Open Door')).toBeInTheDocument()
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
  })

  it('"Choose who to be" resets the identity and goes to the landing page', async () => {
    const api = installFakeApi('priya')
    const { queryClient, user, router } = renderApp({ at: '/ask' })
    await screen.findByRole('heading', {
      level: 1,
      name: /^Good (morning|afternoon|evening), Priya\.$/,
    })
    api.expire()
    await act(() => queryClient.invalidateQueries())
    await heading('This sandbox has reset.')
    queryClient.setQueryData(['the-old-persons-data'], 'stale')
    await user.click(screen.getByRole('button', { name: 'Choose who to be' }))
    expect(await heading('Your open-door policy, now always open.')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/')
    expect(queryClient.getQueryData(['the-old-persons-data'])).toBeUndefined()
  })
})

describe('the not-found page', () => {
  it('shows inside the session for an unknown route, with its title focused', async () => {
    installFakeApi('priya')
    renderApp({ at: '/nowhere', routes: pageRoutes })
    expect(await heading("We couldn't find that page.")).toHaveFocus()
  })

  it('links to /ask through the router, without a page load', async () => {
    installFakeApi('priya')
    const { user, router } = renderApp({ at: '/nowhere' })
    await heading("We couldn't find that page.")
    const link = screen.getByRole('link', { name: 'Go to Ask' })
    expect(link).toHaveAttribute('href', '/ask')
    await user.click(link)
    expect(router.state.location.pathname).toBe('/ask')
  })

  it('shows for an API 404, through the same helper the profile will use', async () => {
    installFakeApi('priya')
    failBoom(404)
    renderApp({ at: '/ask', routes: pageRoutes })
    expect(await heading("We couldn't find that page.")).toHaveFocus()
    expect(screen.getByRole('link', { name: 'Go to Ask' })).toBeInTheDocument()
  })

  it('recognizes only a 404 ApiError as not found', async () => {
    const { ApiError } = await import('@/lib/api-fetch')
    expect(isNotFound(new ApiError(404, null, null))).toBe(true)
    expect(isNotFound(new ApiError(500, null, null))).toBe(false)
    expect(isNotFound(new ApiError(403, null, null))).toBe(false)
    expect(isNotFound(new Error('404'))).toBe(false)
    expect(isNotFound(undefined)).toBe(false)
  })
})

describe('the something-went-wrong page', () => {
  it('shows inside the session for a 5xx, with the full request ID and its title focused', async () => {
    installFakeApi('priya')
    failBoom(500)
    renderApp({ at: '/ask', routes: pageRoutes })
    expect(await heading('Something went wrong on our side.')).toHaveFocus()
    expect(
      screen.getByText(
        'Try again in a moment. If it keeps happening, this reference helps us find it:',
      ),
    ).toBeInTheDocument()
    const reference = screen.getByText(REQUEST_ID)
    expect(reference.textContent).toHaveLength(32)
    expect(reference.tagName).toBe('CODE')
  })

  it('shows inside the session for a network failure, with no reference', async () => {
    installFakeApi('priya')
    server.use(http.get(BOOM(), () => HttpResponse.error()))
    renderApp({ at: '/ask', routes: pageRoutes })
    await heading('Something went wrong on our side.')
    expect(screen.queryByText('Reference')).not.toBeInTheDocument()
  })

  it('Retry repeats the failed request and shows the page', async () => {
    installFakeApi('priya')
    failBoom(500)
    const { user } = renderApp({ at: '/ask', routes: pageRoutes })
    await heading('Something went wrong on our side.')
    server.use(http.get(BOOM(), () => HttpResponse.json({ text: 'it worked' })))
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('it worked')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 1 })).not.toBeInTheDocument()
  })

  it('shows outside the shell when the first /me fails, with the full request ID and a focused title', async () => {
    const api = installFakeApi('priya')
    api.failMe(500)
    renderApp({ at: '/ask' })
    const title = await heading('Something went wrong on our side.')
    expect(title).toHaveFocus()
    expect(screen.getByText('a'.repeat(32))).toBeInTheDocument()
    expect(screen.getByText('Open Door')).toBeInTheDocument()
  })

  it('Retry after a failed first /me loads the signed-in page', async () => {
    const api = installFakeApi('priya')
    api.failMe(500)
    const { user } = renderApp({ at: '/ask' })
    await heading('Something went wrong on our side.')
    api.failMe(null)
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(
      await screen.findByRole('heading', {
        level: 1,
        name: /^Good (morning|afternoon|evening), Priya\.$/,
      }),
    ).toBeInTheDocument()
  })

  it('shows no reference when the failed first /me had no request ID', async () => {
    installFakeApi('priya')
    server.use(http.get(`${window.location.origin}/api/v1/me`, () => HttpResponse.error()))
    renderApp({ at: '/ask' })
    await heading('Something went wrong on our side.')
    expect(within(document.body).queryByText('Reference')).not.toBeInTheDocument()
  })
})

describe('the root error boundary', () => {
  function Throws(): never {
    throw new Error('render failed')
  }

  it('shows "Something went wrong" outside the shell when a page outside the guard throws', async () => {
    installFakeApi()
    const root = routes[0]!
    const withBoom: RouteObject[] = [
      {
        element: root.element,
        errorElement: root.errorElement,
        children: [...(root.children ?? []), { path: '/boom', element: <Throws /> }],
      },
    ]
    renderApp({ at: '/boom', routes: withBoom })
    expect(await heading('Something went wrong on our side.')).toHaveFocus()
    expect(screen.getByText('Open Door')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(screen.queryByText(/Unexpected Application Error/)).not.toBeInTheDocument()
  })
})
