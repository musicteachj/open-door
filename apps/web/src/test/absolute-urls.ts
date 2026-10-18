import { vi } from 'vitest'

// Node's fetch needs an absolute URL; the app passes a path such as "/api/v1/me".
export function stubAbsoluteUrls() {
  const realFetch = globalThis.fetch
  vi.stubGlobal('fetch', (input: RequestInfo | URL, init?: RequestInit) =>
    realFetch(typeof input === 'string' ? `${window.location.origin}${input}` : input, init),
  )
}
