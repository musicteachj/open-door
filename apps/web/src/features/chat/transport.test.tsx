import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useChatTransport, type ChatTransport } from './transport'
import { ChatTransportProvider } from './transport-provider'

describe('useChatTransport', () => {
  it('returns the provided transport', () => {
    const transport: ChatTransport = { send: () => Promise.resolve({ text: 'x' }) }
    const { result } = renderHook(() => useChatTransport(), {
      wrapper: ({ children }) => (
        <ChatTransportProvider transport={transport}>{children}</ChatTransportProvider>
      ),
    })
    expect(result.current).toBe(transport)
  })

  it('falls back to the fake until Phase 4', async () => {
    const { result } = renderHook(() => useChatTransport())
    const reply = await result.current.send('Hi', { signal: new AbortController().signal })
    expect(reply.text).toMatch(/isn't connected yet/)
  })
})
