import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getGetMeQueryKey } from '@/api/generated'
import { SESSION_CHANNEL_NAME, announceSessionChange } from '@/lib/session-channel'
import { useSessionChannel } from './use-session-channel'

class StubChannel {
  static open = new Set<StubChannel>()
  onmessage: ((event: { data: unknown }) => void) | null = null
  name: string
  constructor(name: string) {
    this.name = name
    StubChannel.open.add(this)
  }
  postMessage(data: unknown) {
    for (const other of StubChannel.open)
      if (other !== this && other.name === this.name) other.onmessage?.({ data })
  }
  close() {
    StubChannel.open.delete(this)
  }
}

function anotherTabPosts(kind: string) {
  const other = new StubChannel(SESSION_CHANNEL_NAME)
  other.postMessage({ kind, from: 'another-tab' })
  other.close()
}

describe('useSessionChannel', () => {
  beforeEach(() => {
    StubChannel.open.clear()
    vi.stubGlobal('BroadcastChannel', StubChannel)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function setup() {
    const queryClient = new QueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
    const view = renderHook(() => useSessionChannel(), { wrapper })
    return { invalidate, view }
  }

  it('refetches /me once for a message from another tab', () => {
    const { invalidate } = setup()
    anotherTabPosts('sign-out')
    expect(invalidate).toHaveBeenCalledTimes(1)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: getGetMeQueryKey() })
  })

  it("does not refetch for this tab's own announcement", () => {
    const { invalidate } = setup()
    announceSessionChange('switch')
    expect(invalidate).not.toHaveBeenCalled()
  })

  it('stops listening when the root unmounts', () => {
    const { invalidate, view } = setup()
    view.unmount()
    anotherTabPosts('switch')
    expect(invalidate).not.toHaveBeenCalled()
  })
})
