import { createContext, use } from 'react'
import { createFakeTransport } from './fake-transport'

/** How the assistant home reaches the assistant. Phase 4 adds a real one behind this interface. */
export type ChatTransport = {
  /** Rejects when the signal aborts, or when the send fails. */
  send(question: string, options: { signal: AbortSignal }): Promise<{ text: string }>
}

// Until Phase 4, the default is the fake. Tests and the browser harness provide their own through
// ChatTransportProvider (transport-provider.tsx).
export const TransportContext = createContext<ChatTransport>(createFakeTransport())

export function useChatTransport(): ChatTransport {
  return use(TransportContext)
}
