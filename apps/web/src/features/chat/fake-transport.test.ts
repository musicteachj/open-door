import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createFakeTransport, FAKE_REPLY } from './fake-transport'

beforeEach(() => {
  vi.useFakeTimers()
})
afterEach(() => {
  vi.useRealTimers()
})

describe('fake transport', () => {
  it("replies with the spec's fixed text, word for word", () => {
    expect(FAKE_REPLY).toBe(
      "The assistant isn't connected yet. When it is, it will answer here and cite the Juniper Row handbook for every policy it mentions.",
    )
  })

  it('waits about 400 ms by default, then replies', async () => {
    const transport = createFakeTransport()
    let result: { text: string } | undefined
    void transport.send('Hi', { signal: new AbortController().signal }).then((r) => (result = r))
    await vi.advanceTimersByTimeAsync(399)
    expect(result).toBeUndefined()
    await vi.advanceTimersByTimeAsync(1)
    expect(result).toEqual({ text: FAKE_REPLY })
  })

  it('takes the delay as an option', async () => {
    const transport = createFakeTransport({ delayMs: 0 })
    const promise = transport.send('Hi', { signal: new AbortController().signal })
    await Promise.all([
      expect(promise).resolves.toEqual({ text: FAKE_REPLY }),
      vi.advanceTimersByTimeAsync(0),
    ])
  })

  it('rejects when the signal aborts, and stops waiting', async () => {
    const transport = createFakeTransport()
    const controller = new AbortController()
    const promise = transport.send('Hi', { signal: controller.signal })
    await Promise.all([
      expect(promise).rejects.toMatchObject({ name: 'AbortError' }),
      Promise.resolve().then(() => controller.abort()),
    ])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('rejects at once when the signal is already aborted', async () => {
    const controller = new AbortController()
    controller.abort()
    const promise = createFakeTransport().send('Hi', { signal: controller.signal })
    await expect(promise).rejects.toMatchObject({ name: 'AbortError' })
  })

  it('can be told to fail, for the error state', async () => {
    const transport = createFakeTransport({ delayMs: 0, fail: true })
    const promise = transport.send('Hi', { signal: new AbortController().signal })
    await Promise.all([
      expect(promise).rejects.toThrow('The fake transport was told to fail.'),
      vi.advanceTimersByTimeAsync(0),
    ])
  })
})
