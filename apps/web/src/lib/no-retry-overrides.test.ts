// The retry rules live only in src/lib/query-client.ts. A per-call `retry` can swallow a 401 so
// onUnauthorized never runs, or resend a write after a 403. This scan fails on any other source
// file that sets `retry` or `retryDelay`, the way no-raw-colors guards colors.
import { describe, expect, it } from 'vitest'

const sources = import.meta.glob(['../**/*.{ts,tsx}', '!../**/*.test.{ts,tsx}'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const EXEMPT = ['./query-client.ts', '../api/generated.ts']
// `retry:`, `retry =`, `retryDelay:`, and `retryDelay =`, as an option or a variable.
const RETRY_OPTION = /\bretry(?:Delay)?\s*[:=](?!=)/g

describe('no retry overrides outside the query client', () => {
  it('scans some files, so it cannot pass by checking nothing', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(0)
    expect(Object.keys(sources)).toContain('./query-client.ts')
  })

  it('finds no retry or retryDelay option in any other source file', () => {
    const found = Object.entries(sources)
      .filter(([file]) => !EXEMPT.includes(file))
      .flatMap(([file, source]) =>
        [...source.matchAll(RETRY_OPTION)].map((m) => `${file}: ${m[0]}`),
      )
    expect(found).toEqual([])
  })
})
