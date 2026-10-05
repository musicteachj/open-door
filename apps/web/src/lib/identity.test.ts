import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { registerReset, resetIdentity } from './identity'

describe('resetIdentity', () => {
  it('clears the query cache', () => {
    const client = new QueryClient()
    client.setQueryData(['me'], { name: 'Ada' })
    resetIdentity(client)
    expect(client.getQueryData(['me'])).toBeUndefined()
  })

  it('clears the cache before it runs the resets', () => {
    const client = new QueryClient()
    client.setQueryData(['me'], { name: 'Ada' })
    let seen: unknown = 'unset'
    const unregister = registerReset(() => {
      seen = client.getQueryData(['me'])
    })
    resetIdentity(client)
    unregister()
    expect(seen).toBeUndefined()
  })

  it('calls every registered reset', () => {
    const first = vi.fn<() => void>()
    const second = vi.fn<() => void>()
    const offFirst = registerReset(first)
    const offSecond = registerReset(second)
    resetIdentity(new QueryClient())
    offFirst()
    offSecond()
    expect(first).toHaveBeenCalledTimes(1)
    expect(second).toHaveBeenCalledTimes(1)
  })

  it('stops calling a reset once it is unregistered', () => {
    const reset = vi.fn<() => void>()
    registerReset(reset)()
    resetIdentity(new QueryClient())
    expect(reset).not.toHaveBeenCalled()
  })

  it('runs the other resets even when one throws', () => {
    const after = vi.fn<() => void>()
    const offBad = registerReset(() => {
      throw new Error('boom')
    })
    const offAfter = registerReset(after)
    expect(() => resetIdentity(new QueryClient())).toThrow('boom')
    offBad()
    offAfter()
    expect(after).toHaveBeenCalledTimes(1)
  })
})
