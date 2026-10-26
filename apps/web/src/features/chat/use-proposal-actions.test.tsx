import { QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useShellToast } from '@/features/shell/toast-store'
import { resetIdentity } from '@/lib/identity'
import { createQueryClient } from '@/lib/query-client'
import { stubAbsoluteUrls } from '@/test/absolute-urls'
import { PROPOSAL_ID, conversationOut, proposalOut } from '@/test/fake-assistant'
import { server } from '@/test/msw'
import { useProposalActions } from './use-proposal-actions'

const url = (path: string) => `${window.location.origin}${path}`

function setup() {
  const queryClient = createQueryClient({ onUnauthorized: vi.fn<() => void>(), retryDelayMs: 0 })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return { queryClient, wrapper }
}

/** Holds the confirm's answer until `release` is called, and counts every read afterward. */
function installApi(answer: () => Response) {
  let release!: () => void
  const held = new Promise<void>((resolve) => {
    release = resolve
  })
  const reads = { conversation: 0, budget: 0 }
  server.use(
    http.post(url('/api/v1/assistant/proposals/:id/confirm'), async () => {
      await held
      return answer()
    }),
    http.get(url('/api/v1/assistant/conversations/current'), () => {
      reads.conversation++
      return HttpResponse.json(conversationOut())
    }),
    http.get(url('/api/v1/assistant/budget'), () => {
      reads.budget++
      return HttpResponse.json({})
    }),
  )
  return { release, reads }
}

beforeEach(() => {
  stubAbsoluteUrls()
})
afterEach(() => {
  resetIdentity(setup().queryClient)
})

describe('a confirm in flight when the person changes', () => {
  it.each([
    ['succeeds', () => HttpResponse.json(proposalOut({ status: 'executed' }))],
    ['fails', () => new HttpResponse(null, { status: 500 })],
  ] as const)(
    'leaves nothing of the old person in the new cache, and no toast, when it %s',
    async (_name, answer) => {
      const { release, reads } = installApi(answer)
      const { queryClient, wrapper } = setup()
      const setQueryData = vi.spyOn(queryClient, 'setQueryData')
      const { result } = renderHook(() => useProposalActions(PROPOSAL_ID), { wrapper })
      act(() => result.current.confirm(null))
      await waitFor(() => expect(result.current.confirming).toBe(true))

      act(() => resetIdentity(queryClient))
      release()
      await waitFor(() => expect(result.current.confirming).toBe(false))

      expect(setQueryData).not.toHaveBeenCalled()
      expect(queryClient.getQueryCache().getAll()).toHaveLength(0)
      expect(reads).toEqual({ conversation: 0, budget: 0 })
      expect(useShellToast.getState().message).toBeNull()
    },
  )
})
