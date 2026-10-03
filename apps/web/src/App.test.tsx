import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
}

function stubHealth(body: unknown, status: number) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(body), { status })),
  )
}

describe('App', () => {
  it('shows the product name', () => {
    stubHealth({ status: 'ok', database: 'ok', version: '0.0.0' }, 200)
    renderApp()
    expect(screen.getByRole('heading', { name: 'Open Door' })).toBeInTheDocument()
  })

  it('reports a healthy API', async () => {
    stubHealth({ status: 'ok', database: 'ok', version: '0.0.0' }, 200)
    renderApp()
    expect(await screen.findByText('API: ok')).toBeInTheDocument()
  })

  it('reports a degraded API when the database is down', async () => {
    stubHealth({ status: 'degraded', database: 'unavailable', version: '0.0.0' }, 503)
    renderApp()
    expect(await screen.findByText('API: degraded')).toBeInTheDocument()
  })

  it('reports an unreachable API when the request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch')
      }),
    )
    renderApp()
    expect(await screen.findByText('API: unreachable')).toBeInTheDocument()
  })

  it('reports an unreachable API when the proxy answers with an empty error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(null, { status: 502 })),
    )
    renderApp()
    expect(await screen.findByText('API: unreachable')).toBeInTheDocument()
  })

  it('reports an unreachable API when the health check itself errors', async () => {
    stubHealth({ type: 'about:blank', title: 'Internal Server Error', status: 500 }, 500)
    renderApp()
    expect(await screen.findByText('API: unreachable')).toBeInTheDocument()
  })
})
