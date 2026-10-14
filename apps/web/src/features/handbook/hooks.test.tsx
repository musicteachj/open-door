import { QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createQueryClient } from '@/lib/query-client'
import { californiaSickLeave, passageView } from '@/test/handbook-fixtures'
import { installFakeHandbook } from '@/test/fake-handbook'
import { server } from '@/test/msw'
import { useHandbook } from './use-handbook'
import { useHandbookSearch } from './use-handbook-search'
import { usePassage } from './use-passage'
import { useSection } from './use-section'

const url = (path: string) => `${window.location.origin}${path}`

beforeEach(() => {
  const realFetch = globalThis.fetch
  vi.stubGlobal('fetch', (input: RequestInfo | URL, init?: RequestInit) =>
    realFetch(typeof input === 'string' ? url(input) : input, init),
  )
})

function wrapper() {
  const client = createQueryClient({ onUnauthorized: () => {}, retryDelayMs: 0 })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

const problem = (status: number) =>
  HttpResponse.json({ type: 'about:blank', title: 'No', status, instance: '/' }, { status })

describe('useHandbook', () => {
  it('reads the version and every section', async () => {
    installFakeHandbook('priya')
    const { result } = renderHook(() => useHandbook(), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.data).toBeDefined())
    expect(result.current.data?.version.label).toBe('2026.10')
    expect(result.current.data?.sections).toHaveLength(34)
  })
})

describe('useHandbookSearch', () => {
  it('asks nothing for an empty or blank query', async () => {
    const api = installFakeHandbook('priya')
    const { result } = renderHook(() => useHandbookSearch('   '), { wrapper: wrapper() })
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(result.current.fetchStatus).toBe('idle')
    expect(api.searches()).toEqual([])
  })

  it('sends the trimmed query, capped at 100 characters', async () => {
    const api = installFakeHandbook('priya')
    const { result } = renderHook(() => useHandbookSearch(`  ${'a'.repeat(130)}  `), {
      wrapper: wrapper(),
    })
    await waitFor(() => expect(result.current.data).toBeDefined())
    expect(api.searches()).toEqual(['a'.repeat(100)])
  })
})

describe('useSection', () => {
  it('maps a 404 to the missing state, not an error to throw', async () => {
    server.use(http.get(url('/api/v1/handbook/sections/8.2'), () => problem(404)))
    const { result } = renderHook(() => useSection('8.2'), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.missing).toBe(true))
    expect(result.current.data).toBeUndefined()
  })

  it('is not missing while it loads or after it loads', async () => {
    server.use(
      http.get(url('/api/v1/handbook/sections/CA-4.3'), () =>
        HttpResponse.json({ section: californiaSickLeave() }),
      ),
    )
    const { result } = renderHook(() => useSection('CA-4.3'), { wrapper: wrapper() })
    expect(result.current.missing).toBe(false)
    await waitFor(() => expect(result.current.data).toBeDefined())
    expect(result.current.missing).toBe(false)
  })

  it('encodes the ID so it cannot reach another path', async () => {
    let seen = ''
    server.use(
      http.get(url('/api/v1/handbook/sections/:id'), ({ request }) => {
        seen = new URL(request.url).pathname
        return problem(404)
      }),
    )
    const { result } = renderHook(() => useSection('../me'), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.missing).toBe(true))
    expect(seen).toBe('/api/v1/handbook/sections/..%2Fme')
  })

  // Encoding leaves "." and "..", and the URL parser would resolve them as a step up the path. An
  // empty ID would ask for the section list's own path.
  it.each(['', '.', '..'])('takes %j as missing, asking nothing', async (id) => {
    const seen: string[] = []
    server.use(
      http.get(url('/api/v1/*'), ({ request }) => {
        seen.push(new URL(request.url).pathname)
        return problem(404)
      }),
    )
    const { result } = renderHook(() => useSection(id), { wrapper: wrapper() })
    expect(result.current.missing).toBe(true)
    expect(result.current.fetchStatus).toBe('idle')
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(result.current.fetchStatus).toBe('idle')
    expect(seen).toEqual([])
  })
})

describe('usePassage', () => {
  it('asks nothing without both IDs', async () => {
    const { result } = renderHook(() => usePassage('CA-4.3', null), { wrapper: wrapper() })
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(result.current.fetchStatus).toBe('idle')
  })

  it.each([
    ['..', 'p2'],
    ['CA-4.3', '..'],
    ['CA-4.3', '.'],
  ])('asks nothing for %j and %j, which would reach another path', async (section, passage) => {
    const seen: string[] = []
    server.use(
      http.get(url('/api/v1/*'), ({ request }) => {
        seen.push(new URL(request.url).pathname)
        return problem(404)
      }),
    )
    const { result } = renderHook(() => usePassage(section, passage), { wrapper: wrapper() })
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(result.current.fetchStatus).toBe('idle')
    expect(seen).toEqual([])
  })

  it('reads the passage with its neighbors', async () => {
    server.use(
      http.get(url('/api/v1/handbook/sections/CA-4.3/passages/p2'), () =>
        HttpResponse.json(passageView()),
      ),
    )
    const { result } = renderHook(() => usePassage('CA-4.3', 'p2'), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.data?.passage.id).toBe('p2'))
  })
})
