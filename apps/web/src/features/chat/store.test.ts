import { QueryClient } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { resetIdentity } from '@/lib/identity'
import { useChatStore } from './store'
import type { ChatTransport } from './transport'

type Deferred = {
  question: string
  signal: AbortSignal
  resolve: (text: string) => void
  reject: (error: Error) => void
}

/** A transport the test settles by hand. */
function manualTransport() {
  const calls: Deferred[] = []
  const transport: ChatTransport = {
    send: (question, { signal }) =>
      new Promise((resolve, reject) => {
        calls.push({ question, signal, resolve: (text) => resolve({ text }), reject })
      }),
  }
  return { transport, calls }
}

const state = () => useChatStore.getState()

beforeEach(() => {
  resetIdentity(new QueryClient())
})
afterEach(() => {
  resetIdentity(new QueryClient())
})

describe('chat store', () => {
  it('starts empty', () => {
    expect(state()).toMatchObject({ draft: '', status: 'idle', reply: null, lastQuestion: null })
  })

  it('keeps the draft the person types', () => {
    state().setDraft('How many sick days do I get?')
    expect(state().draft).toBe('How many sick days do I get?')
  })

  it('sends a question and shows the reply, emptying the draft', async () => {
    const { transport, calls } = manualTransport()
    state().setDraft('Hello')
    const sent = state().send(transport, 'Hello')
    expect(state().status).toBe('sending')
    expect(state().lastQuestion).toBe('Hello')
    calls[0]!.resolve('Hi there')
    await sent
    expect(state()).toMatchObject({
      status: 'replied',
      reply: 'Hi there',
      lastQuestion: 'Hello',
      draft: '',
    })
  })

  it('clears the earlier reply when a new send starts, and after a failure', async () => {
    const { transport, calls } = manualTransport()
    const first = state().send(transport, 'One')
    calls[0]!.resolve('first reply')
    await first
    const second = state().send(transport, 'Two')
    expect(state().reply).toBeNull()
    calls[1]!.reject(new Error('network'))
    await second
    expect(state()).toMatchObject({ status: 'failed', reply: null })
  })

  it('keeps what was typed while the reply was pending', async () => {
    const { transport, calls } = manualTransport()
    state().setDraft('Hello')
    const sent = state().send(transport, 'Hello')
    state().setDraft('Hello, and also')
    calls[0]!.resolve('Hi')
    await sent
    expect(state().draft).toBe('Hello, and also')
  })

  it('keeps the question and the draft when the send fails', async () => {
    const { transport, calls } = manualTransport()
    state().setDraft('Hello')
    const sent = state().send(transport, 'Hello')
    calls[0]!.reject(new Error('network'))
    await sent
    expect(state()).toMatchObject({
      status: 'failed',
      lastQuestion: 'Hello',
      draft: 'Hello',
      reply: null,
    })
  })

  it('ignores a send while one is in flight', async () => {
    const { transport, calls } = manualTransport()
    const first = state().send(transport, 'One')
    await state().send(transport, 'Two')
    expect(calls).toHaveLength(1)
    expect(state().lastQuestion).toBe('One')
    calls[0]!.resolve('ok')
    await first
    expect(state().reply).toBe('ok')
  })

  it('ignores a blank question', async () => {
    const { transport, calls } = manualTransport()
    await state().send(transport, '   ')
    expect(calls).toHaveLength(0)
    expect(state().status).toBe('idle')
  })

  it('empties on an identity reset', async () => {
    const { transport, calls } = manualTransport()
    state().setDraft('draft')
    const sent = state().send(transport, 'Hello')
    calls[0]!.resolve('Hi')
    await sent
    resetIdentity(new QueryClient())
    expect(state()).toMatchObject({ draft: '', status: 'idle', reply: null, lastQuestion: null })
  })

  it('aborts a send in flight on reset, and drops its late reply', async () => {
    const { transport, calls } = manualTransport()
    const sent = state().send(transport, 'Hello')
    resetIdentity(new QueryClient())
    expect(calls[0]!.signal.aborted).toBe(true)
    // A transport that ignores the signal still answers late.
    calls[0]!.resolve('for the old person')
    await sent
    expect(state()).toMatchObject({ status: 'idle', reply: null, lastQuestion: null })
  })

  it('drops a late failure after a reset', async () => {
    const { transport, calls } = manualTransport()
    const sent = state().send(transport, 'Hello')
    resetIdentity(new QueryClient())
    calls[0]!.reject(new Error('late'))
    await sent
    expect(state().status).toBe('idle')
  })

  it('lets the next person send after a reset, and shows only their reply', async () => {
    const { transport, calls } = manualTransport()
    const old = state().send(transport, 'Old question')
    resetIdentity(new QueryClient())
    const next = state().send(transport, 'New question')
    expect(state().status).toBe('sending')
    calls[0]!.resolve('old reply')
    calls[1]!.resolve('new reply')
    await Promise.all([old, next])
    expect(state()).toMatchObject({ reply: 'new reply', lastQuestion: 'New question' })
  })
})
