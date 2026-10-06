import { create } from 'zustand'
import { registerReset } from '@/lib/identity'
import type { ChatTransport } from './transport'

type ChatStatus = 'idle' | 'sending' | 'replied' | 'failed'

type ChatState = {
  draft: string
  status: ChatStatus
  reply: string | null
  /** The question last sent. */
  lastQuestion: string | null
  setDraft: (draft: string) => void
  /** Sends a question. Ignored while a send is in flight, or when the question is blank. */
  send: (transport: ChatTransport, question: string) => Promise<void>
}

const EMPTY = { draft: '', status: 'idle', reply: null, lastQuestion: null } as const

// Each send belongs to one generation. A reset starts a new one and aborts the send in flight, so
// a late reply (even from a transport that ignores the signal) never reaches the next person.
let generation = 0
let inFlight: AbortController | null = null

export const useChatStore = create<ChatState>((set, get) => ({
  ...EMPTY,
  setDraft: (draft) => set({ draft }),
  async send(transport, question) {
    if (get().status === 'sending' || question.trim() === '') return
    const mine = ++generation
    const controller = new AbortController()
    inFlight = controller
    set({ status: 'sending', lastQuestion: question, reply: null })
    try {
      const { text } = await transport.send(question, { signal: controller.signal })
      if (mine !== generation) return
      set((state) => ({
        status: 'replied',
        reply: text,
        // Keep anything typed while the reply was pending.
        draft: state.draft === question ? '' : state.draft,
      }))
    } catch {
      if (mine !== generation) return
      set({ status: 'failed' })
    } finally {
      if (inFlight === controller) inFlight = null
    }
  },
}))

registerReset(() => {
  generation++
  inFlight?.abort()
  inFlight = null
  useChatStore.setState(EMPTY)
})
