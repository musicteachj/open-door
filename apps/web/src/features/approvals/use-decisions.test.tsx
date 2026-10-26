import { QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PRIYA_WAITING } from '@/app/gallery/fixtures/timeoff'
import { createQueryClient } from '@/lib/query-client'
import { stubAbsoluteUrls } from '@/test/absolute-urls'
import { server } from '@/test/msw'
import { useDecisions } from './use-decisions'

// Where focus goes after a decision is worked out from the cards as they were when the decision
// started. The queue is read again while the write is still ending, and a draw that lands first
// has already lost the decided card, so the order read afterward would point at the first card.

const url = (path: string) => `${window.location.origin}${path}`
const THREE = ['first', 'middle', 'last']

function setup() {
  const queryClient = createQueryClient({ onUnauthorized: vi.fn<() => void>(), retryDelayMs: 0 })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  const page = { live: THREE, order: THREE }
  const hook = renderHook(() => useDecisions({ personId: 'marcus', layout: () => page }), {
    wrapper,
  })
  return { hook, page }
}

/** The page has drawn again without the middle card by the time the server has answered. */
function answer(page: { live: string[]; order: string[] }, status: number) {
  server.use(
    http.post(url('/api/v1/time-off/requests/:id/decision'), () => {
      page.live = ['first', 'last']
      return status === 409
        ? HttpResponse.json(
            {
              type: 'status-changed',
              title: 'status-changed',
              status: 409,
              instance: '/x',
              detail: 'Changed.',
              currentStatus: 'canceled',
            },
            { status: 409 },
          )
        : HttpResponse.json({ ...PRIYA_WAITING, status: 'approved' })
    }),
  )
}

beforeEach(() => {
  stubAbsoluteUrls()
})

describe('useDecisions: where focus goes', () => {
  it.each([200, 409])(
    'goes to the card after the decided one even when the page has drawn without it (%i)',
    async (status) => {
      const { hook, page } = setup()
      answer(page, status)
      const opener = document.createElement('button')
      await act(async () => {
        hook.result.current.begin('approve', { ...PRIYA_WAITING, id: 'middle' }, opener)
      })
      act(() => hook.result.current.confirm())
      await waitFor(() => expect(hook.result.current.open).toBeNull())
      expect(hook.result.current.focusPlan()).toEqual({ to: 'request', id: 'last' })
    },
  )
})
