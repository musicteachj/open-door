import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { server } from '@/test/msw'
import { ApiError, apiFetch } from './api-fetch'

// Node's fetch needs an absolute URL. The app itself passes a path such as "/api/health".
const url = (path: string) => `${window.location.origin}${path}`

// The real cookie is `__Host-`, so jsdom insists on Secure and Path=/.
function setCsrf(value: string) {
  document.cookie = `__Host-od_csrf=${value}; Secure; Path=/`
}
function clearCookies() {
  for (const part of document.cookie.split('; ')) {
    const name = part.split('=')[0]
    if (name) document.cookie = `${name}=; Secure; Path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`
  }
}

// Records the headers of the last request and answers 200 with a small body.
function recordHeaders() {
  const seen: { headers: Headers | null } = { headers: null }
  server.use(
    http.all(url('/api/echo'), ({ request }) => {
      seen.headers = request.headers
      return HttpResponse.json({ ok: true })
    }),
  )
  return seen
}

afterEach(clearCookies)

describe('apiFetch CSRF header', () => {
  it.each(['POST', 'PUT', 'PATCH', 'DELETE'])(
    'sends the cookie as X-CSRF-Token on %s',
    async (method) => {
      setCsrf('token-1')
      const seen = recordHeaders()
      await apiFetch(url('/api/echo'), { method })
      expect(seen.headers?.get('X-CSRF-Token')).toBe('token-1')
    },
  )

  // An audited read (a case's words, a person's private details) needs the header too.
  it.each(['GET', 'HEAD'])('sends X-CSRF-Token on %s to its own /api/ paths', async (method) => {
    setCsrf('token-1')
    const seen = recordHeaders()
    await apiFetch(url('/api/echo'), { method })
    expect(seen.headers?.get('X-CSRF-Token')).toBe('token-1')
  })

  it.each(['/health', '/apiary/echo', '/other/api/echo', '/assets/app.js'])(
    'never sends the token to the same origin outside /api/: %s',
    async (target) => {
      expect(await tokenSentTo(target, 'GET')).toBeNull()
    },
  )

  it('refuses redirects on its own /api/ requests', async () => {
    const stub = vi.fn<typeof fetch>(async () => new Response('{}'))
    vi.stubGlobal('fetch', stub)
    await apiFetch('/api/echo')
    expect(stub.mock.calls[0]?.[1]?.redirect).toBe('error')
  })

  it('sends nothing when there is no cookie', async () => {
    const seen = recordHeaders()
    await apiFetch(url('/api/echo'), { method: 'POST' })
    expect(seen.headers?.has('X-CSRF-Token')).toBe(false)
  })

  it('reads the cookie fresh on every call', async () => {
    const seen = recordHeaders()
    setCsrf('first')
    await apiFetch(url('/api/echo'), { method: 'POST' })
    expect(seen.headers?.get('X-CSRF-Token')).toBe('first')
    setCsrf('second')
    await apiFetch(url('/api/echo'), { method: 'POST' })
    expect(seen.headers?.get('X-CSRF-Token')).toBe('second')
  })

  it('ignores another cookie whose name only ends the same way', async () => {
    document.cookie = 'x__Host-od_csrf=wrong; Path=/'
    document.cookie = '__Host-od_csrf_old=wrong; Secure; Path=/'
    const seen = recordHeaders()
    await apiFetch(url('/api/echo'), { method: 'POST' })
    expect(seen.headers?.has('X-CSRF-Token')).toBe(false)
  })

  it('does not decode the value, because the API compares the raw token', async () => {
    setCsrf('a%2Fb')
    const seen = recordHeaders()
    await apiFetch(url('/api/echo'), { method: 'POST' })
    expect(seen.headers?.get('X-CSRF-Token')).toBe('a%2Fb')
  })
})

// A stubbed fetch lets the test pass the URLs a browser accepts but Node's fetch does not, such as
// a bare path or "//host".
async function tokenSentTo(target: string, method = 'POST') {
  setCsrf('token-1')
  const stub = vi.fn<typeof fetch>(async () => new Response('{}'))
  vi.stubGlobal('fetch', stub)
  await apiFetch(target, { method })
  return new Headers(stub.mock.calls[0]?.[1]?.headers).get('X-CSRF-Token')
}

describe('apiFetch origin check', () => {
  it.each(['https://evil.example/api/echo', '//evil.example/api/echo'])(
    'never sends the token to %s',
    async (target) => {
      expect(await tokenSentTo(target)).toBeNull()
    },
  )

  it.each(['/api/echo', `${window.location.origin}/api/echo`])(
    'still sends the token to %s',
    async (target) => {
      expect(await tokenSentTo(target)).toBe('token-1')
    },
  )

  it('judges a bare relative path against the page URL, as fetch resolves it', async () => {
    window.history.pushState({}, '', '/ask/abc')
    try {
      expect(await tokenSentTo('api/x')).toBeNull()
      expect(await tokenSentTo('/api/x')).toBe('token-1')
    } finally {
      window.history.pushState({}, '', '/')
    }
  })

  it('keeps credentials same-origin even when the caller asks for include', async () => {
    let credentials: string | null = null
    server.use(
      http.get(url('/api/echo'), ({ request }) => {
        credentials = request.credentials
        return HttpResponse.json({})
      }),
    )
    await apiFetch(url('/api/echo'), { method: 'GET', credentials: 'include' })
    expect(credentials).toBe('same-origin')
  })
})

describe('apiFetch request shape', () => {
  it('sets the JSON content type when there is a body', async () => {
    const seen = recordHeaders()
    await apiFetch(url('/api/echo'), { method: 'POST', body: JSON.stringify({ a: 1 }) })
    expect(seen.headers?.get('Content-Type')).toBe('application/json')
  })

  it('keeps a content type the caller set', async () => {
    const seen = recordHeaders()
    await apiFetch(url('/api/echo'), {
      method: 'POST',
      body: '{}',
      headers: { 'Content-Type': 'application/merge-patch+json' },
    })
    expect(seen.headers?.get('Content-Type')).toBe('application/merge-patch+json')
  })

  it('sets no content type when there is no body', async () => {
    const seen = recordHeaders()
    await apiFetch(url('/api/echo'), { method: 'GET' })
    expect(seen.headers?.has('Content-Type')).toBe(false)
  })

  it('leaves credentials at the default', async () => {
    let credentials: string | null = null
    server.use(
      http.get(url('/api/echo'), ({ request }) => {
        credentials = request.credentials
        return HttpResponse.json({})
      }),
    )
    await apiFetch(url('/api/echo'), { method: 'GET' })
    expect(credentials).toBe('same-origin')
  })
})

describe('apiFetch results', () => {
  it('returns the parsed body of a success', async () => {
    server.use(http.get(url('/api/thing'), () => HttpResponse.json({ name: 'a' })))
    await expect(apiFetch(url('/api/thing'), { method: 'GET' })).resolves.toEqual({ name: 'a' })
  })

  it('returns undefined for a 204', async () => {
    server.use(http.delete(url('/api/thing'), () => new HttpResponse(null, { status: 204 })))
    await expect(apiFetch(url('/api/thing'), { method: 'DELETE' })).resolves.toBeUndefined()
  })

  it('throws an ApiError for a 200 that is not JSON, such as a proxy page', async () => {
    server.use(http.get(url('/api/thing'), () => HttpResponse.text('<html></html>')))
    expect(await failure('/api/thing')).toMatchObject({ status: 200, problem: null })
  })

  it('returns undefined for an empty 200', async () => {
    server.use(http.get(url('/api/thing'), () => new HttpResponse('', { status: 200 })))
    await expect(apiFetch(url('/api/thing'), { method: 'GET' })).resolves.toBeUndefined()
  })
})

const problemBody = {
  type: 'about:blank',
  title: 'Forbidden',
  status: 403,
  instance: '/api/thing',
  requestId: 'req-1',
}

async function failure(path: string) {
  try {
    await apiFetch(url(path), { method: 'GET' })
  } catch (error) {
    return error
  }
  throw new Error('apiFetch did not throw')
}

describe('apiFetch errors', () => {
  it('throws an ApiError with the status, the problem, and the request ID', async () => {
    server.use(
      http.get(url('/api/thing'), () =>
        HttpResponse.json(problemBody, {
          status: 403,
          headers: { 'Content-Type': 'application/problem+json', 'X-Request-ID': 'req-1' },
        }),
      ),
    )
    const error = await failure('/api/thing')
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 403, problem: problemBody, requestId: 'req-1' })
  })

  it('gives problem null for a JSON body that is not a problem, such as the health 503', async () => {
    server.use(
      http.get(url('/api/thing'), () =>
        HttpResponse.json({ status: 'degraded', data: {} }, { status: 503 }),
      ),
    )
    const error = await failure('/api/thing')
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 503, problem: null, requestId: null })
  })

  it('gives problem null when the title is not a string or the status is not a number', async () => {
    server.use(
      http.get(url('/api/a'), () => HttpResponse.json({ title: 5, status: 400 }, { status: 400 })),
      http.get(url('/api/b'), () =>
        HttpResponse.json({ title: 'x', status: '400' }, { status: 400 }),
      ),
    )
    expect(await failure('/api/a')).toMatchObject({ problem: null })
    expect(await failure('/api/b')).toMatchObject({ problem: null })
  })

  it('gives problem null for an HTML proxy error instead of a parse error', async () => {
    server.use(
      http.get(url('/api/thing'), () =>
        HttpResponse.text('<html>Bad Gateway</html>', {
          status: 502,
          headers: { 'Content-Type': 'text/html' },
        }),
      ),
    )
    const error = await failure('/api/thing')
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 502, problem: null })
  })

  it('gives problem null for a JSON content type with a broken body', async () => {
    server.use(
      http.get(
        url('/api/thing'),
        () =>
          new HttpResponse('{oops', {
            status: 500,
            headers: { 'Content-Type': 'application/json' },
          }),
      ),
    )
    expect(await failure('/api/thing')).toMatchObject({ status: 500, problem: null })
  })

  it('gives problem null for an empty error body', async () => {
    server.use(http.get(url('/api/thing'), () => new HttpResponse(null, { status: 502 })))
    expect(await failure('/api/thing')).toMatchObject({ status: 502, problem: null })
  })
})
