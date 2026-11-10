import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  SESSION_CHANNEL_NAME,
  TAB_ID,
  announceSessionChange,
  listenForSessionChanges,
} from './session-channel'

/** A BroadcastChannel stand-in: a message reaches every OTHER open channel of the same name, as in a browser. */
class StubChannel {
  static open = new Set<StubChannel>()
  static posted: unknown[] = []
  onmessage: ((event: { data: unknown }) => void) | null = null
  closed = false
  name: string
  constructor(name: string) {
    this.name = name
    StubChannel.open.add(this)
  }
  postMessage(data: unknown) {
    StubChannel.posted.push(data)
    for (const other of StubChannel.open)
      if (other !== this && other.name === this.name) other.onmessage?.({ data })
  }
  close() {
    this.closed = true
    StubChannel.open.delete(this)
  }
}

/** Another tab's post, from a channel object of its own. */
function fromAnotherTab(data: unknown) {
  const other = new StubChannel(SESSION_CHANNEL_NAME)
  other.postMessage(data)
  other.close()
}

describe('session channel', () => {
  beforeEach(() => {
    StubChannel.open.clear()
    StubChannel.posted = []
    vi.stubGlobal('BroadcastChannel', StubChannel)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('posts one message on od.session for a switch, a sign-out, or a new sandbox', () => {
    announceSessionChange('switch')
    announceSessionChange('sign-out')
    announceSessionChange('start')
    expect(SESSION_CHANNEL_NAME).toBe('od.session')
    expect(StubChannel.posted).toEqual([
      { kind: 'switch', from: TAB_ID },
      { kind: 'sign-out', from: TAB_ID },
      { kind: 'start', from: TAB_ID },
    ])
  })

  it('carries only the kind and the tab, never a token or a name', () => {
    announceSessionChange('switch')
    const [message] = StubChannel.posted as Record<string, unknown>[]
    expect(Object.keys(message!).sort()).toEqual(['from', 'kind'])
    expect(TAB_ID).toMatch(/^[0-9a-f-]{8,}$/i)
  })

  it('tells another tab, once per message', () => {
    const onChange = vi.fn<(kind: string) => void>()
    const stop = listenForSessionChanges(onChange)
    fromAnotherTab({ kind: 'sign-out', from: 'someone-else' })
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith('sign-out')
    stop()
  })

  it('ignores its own message, even from a different channel object in the same tab', () => {
    const onChange = vi.fn<(kind: string) => void>()
    const stop = listenForSessionChanges(onChange)
    announceSessionChange('switch')
    expect(onChange).not.toHaveBeenCalled()
    stop()
  })

  it('ignores anything that is not a session change', () => {
    const onChange = vi.fn<(kind: string) => void>()
    const stop = listenForSessionChanges(onChange)
    for (const data of [
      null,
      'switch',
      42,
      {},
      { kind: 'switch' },
      { kind: 'wipe', from: 'x' },
      { kind: 'switch', from: 7 },
    ])
      fromAnotherTab(data)
    expect(onChange).not.toHaveBeenCalled()
    stop()
  })

  it('stops listening, and closes its channel, when told to', () => {
    const onChange = vi.fn<(kind: string) => void>()
    const before = StubChannel.open.size
    const stop = listenForSessionChanges(onChange)
    expect(StubChannel.open.size).toBe(before + 1)
    stop()
    expect(StubChannel.open.size).toBe(before)
    fromAnotherTab({ kind: 'switch', from: 'someone-else' })
    expect(onChange).not.toHaveBeenCalled()
  })

  it('does nothing where there is no BroadcastChannel', () => {
    vi.unstubAllGlobals()
    vi.stubGlobal('BroadcastChannel', undefined)
    const onChange = vi.fn<(kind: string) => void>()
    expect(() => announceSessionChange('switch')).not.toThrow()
    const stop = listenForSessionChanges(onChange)
    expect(() => stop()).not.toThrow()
    expect(onChange).not.toHaveBeenCalled()
  })

  it('does not throw if the browser refuses to open a channel', () => {
    vi.stubGlobal(
      'BroadcastChannel',
      class {
        constructor() {
          throw new Error('SecurityError')
        }
      },
    )
    expect(() => announceSessionChange('switch')).not.toThrow()
    expect(() => listenForSessionChanges(vi.fn<(kind: string) => void>())()).not.toThrow()
  })
})
