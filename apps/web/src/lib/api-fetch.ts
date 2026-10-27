import type { Problem } from '@/api/generated'

// The one way the generated client reaches the network (an Orval `override.mutator`). It lives
// outside src/api/ because Orval's `clean` option empties that folder.

const CSRF_COOKIE = '__Host-od_csrf'
const CSRF_HEADER = 'X-CSRF-Token'
const API_PREFIX = '/api/'

/** An error response, or a success response whose body could not be read. */
export class ApiError extends Error {
  readonly status: number
  /** The problem-details body, or null when the body was not one (the health 503, a proxy's 502). */
  readonly problem: Problem | null
  readonly requestId: string | null

  constructor(status: number, problem: Problem | null, requestId: string | null) {
    super(problem?.title ?? `Request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.problem = problem
    this.requestId = requestId
  }
}

/** Orval's mutator convention: every generated hook's `error` is an `ApiError`. */
export type ErrorType<_Error> = ApiError

function isProblem(body: unknown): body is Problem {
  if (typeof body !== 'object' || body === null) return false
  const { title, status } = body as Record<string, unknown>
  return typeof title === 'string' && typeof status === 'number'
}

/**
 * The CSRF token, read fresh from the cookie jar on every call, because creating a sandbox and
 * switching persona both replace it. The name must match exactly, so `x__Host-od_csrf` and
 * `__Host-od_csrf_old` never count. The value is sent as the browser stores it, undecoded.
 */
function readCsrfToken(): string | null {
  for (const part of document.cookie.split(';')) {
    const separator = part.indexOf('=')
    if (separator === -1) continue
    if (part.slice(0, separator).trim() === CSRF_COOKIE) return part.slice(separator + 1).trim()
  }
  return null
}

/** Whether `url` lands on this page's own origin under /api/. `new URL` resolves a relative path,
 * and a protocol-relative "//host", against the page's full URL, as `fetch` does, so the
 * comparison sees where it lands. */
function isOwnApiUrl(url: string): boolean {
  try {
    const target = new URL(url, window.location.href)
    return target.origin === window.location.origin && target.pathname.startsWith(API_PREFIX)
  } catch {
    return false
  }
}

/**
 * Adds the CSRF token to `headers` for a request to this page's own origin under /api/, on any
 * method: an audited read needs it too, because no navigation or cross-site form can send it. The
 * token goes nowhere else. Returns whether `url` is such a request, so the caller can also refuse
 * redirects. Shared with the turn stream's own `fetch` (`stream-turn.ts`), so the rule exists once.
 */
export function applyCsrfHeader(headers: Headers, url: string): boolean {
  if (!isOwnApiUrl(url)) return false
  const token = readCsrfToken()
  if (token !== null) headers.set(CSRF_HEADER, token)
  return true
}

function parseBody(text: string): { body: unknown; parsed: boolean } {
  if (text === '') return { body: undefined, parsed: true }
  try {
    return { body: JSON.parse(text), parsed: true }
  } catch {
    return { body: undefined, parsed: false }
  }
}

/** The `ApiError` for a non-2xx response whose body has been read as `text`. */
export function apiErrorFrom(response: Response, text: string): ApiError {
  const { body, parsed } = parseBody(text)
  return new ApiError(
    response.status,
    parsed && isProblem(body) ? body : null,
    response.headers.get('X-Request-ID'),
  )
}

export async function apiFetch<T>(url: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)

  const ownApi = applyCsrfHeader(headers, url)
  if (init.body != null && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  // Credentials are pinned after the spread, so a caller cannot widen them.
  // A redirect on one of our own requests would carry the token wherever it points, so it fails.
  const response = await fetch(url, {
    ...init,
    method,
    headers,
    credentials: 'same-origin',
    ...(ownApi ? { redirect: 'error' as const } : {}),
  })
  const text = await response.text()

  if (!response.ok) throw apiErrorFrom(response, text)
  const { body, parsed } = parseBody(text)
  // A 2xx the client cannot read, such as an HTML page from a misconfigured proxy, is a failure.
  if (!parsed) throw new ApiError(response.status, null, response.headers.get('X-Request-ID'))
  return body as T
}
