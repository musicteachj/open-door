import type { ReactNode } from 'react'
import { TransportContext, type ChatTransport } from './transport'

export function ChatTransportProvider({
  transport,
  children,
}: {
  transport: ChatTransport
  children: ReactNode
}) {
  return <TransportContext value={transport}>{children}</TransportContext>
}
