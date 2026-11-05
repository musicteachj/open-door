import { http, HttpResponse } from 'msw'
import type { ConsoleMetricsOut, ConsoleTurnOut, ConsoleTurnsPageOut } from '@/api/generated'
import { DAY_METRICS, DAY_TURNS } from '@/app/gallery/fixtures/console'
import { server } from './msw'

// A fake of the console routes for the page tests. It counts every call so a test can say that
// opening a row asked for nothing.

const url = (path: string) => `${window.location.origin}${path}`

export type FakeConsoleOptions = {
  metrics?: ConsoleMetricsOut
  /** The turn pages by cursor ('' is the first page). */
  pages?: Record<string, ConsoleTurnsPageOut>
  /** Status codes for the two routes, to fail them. */
  turnsStatus?: number
  metricsStatus?: number
  /** A page cursor whose read fails with a 500. */
  failCursor?: string
}

export const ONE_PAGE: Record<string, ConsoleTurnsPageOut> = {
  '': { items: DAY_TURNS, nextCursor: null },
}

export function installFakeConsole(options: FakeConsoleOptions = {}) {
  const calls = { turns: [] as (string | null)[], metrics: 0 }
  const state = { ...options }
  server.use(
    http.get(url('/api/v1/console/turns'), ({ request }) => {
      const cursor = new URL(request.url).searchParams.get('cursor')
      calls.turns.push(cursor)
      if (state.failCursor !== undefined && cursor === state.failCursor) {
        return HttpResponse.json({ title: 'Failure', status: 500 }, { status: 500 })
      }
      if (state.turnsStatus) {
        return HttpResponse.json(
          { type: 'about:blank', title: 'Failure', status: state.turnsStatus },
          { status: state.turnsStatus, headers: { 'X-Request-ID': 'c41e8b07'.repeat(4) } },
        )
      }
      const page = (state.pages ?? ONE_PAGE)[cursor ?? '']
      return page ? HttpResponse.json(page) : HttpResponse.json({ items: [], nextCursor: null })
    }),
    http.get(url('/api/v1/console/metrics'), () => {
      calls.metrics++
      if (state.metricsStatus) {
        return HttpResponse.json(
          { type: 'about:blank', title: 'Failure', status: state.metricsStatus },
          { status: state.metricsStatus, headers: { 'X-Request-ID': 'd52f9c18'.repeat(4) } },
        )
      }
      return HttpResponse.json(state.metrics ?? DAY_METRICS)
    }),
  )
  return {
    calls,
    /** Changes what the routes answer from now on. */
    set: (next: Partial<FakeConsoleOptions>) => Object.assign(state, next),
    /** Makes the routes answer again from now on. */
    recover: () => {
      state.turnsStatus = undefined
      state.metricsStatus = undefined
    },
  }
}

export type { ConsoleTurnOut }
