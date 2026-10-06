import { QueryObserver } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { getGetMeQueryKey } from '@/api/generated'
import { ApiError } from './api-fetch'
import { createQueryClient } from './query-client'

function setup() {
  const onUnauthorized = vi.fn<() => void>()
  const client = createQueryClient({ onUnauthorized, retryDelayMs: 0 })
  return { client, onUnauthorized }
}

const apiError = (status: number) => new ApiError(status, null, null)

let runs = 0

/** Runs a read until it settles, and returns how many times its function was called. */
async function runRead(
  client: ReturnType<typeof setup>['client'],
  fail: () => Error,
  key?: readonly unknown[],
) {
  const queryFn = vi.fn<() => Promise<never>>(async () => {
    throw fail()
  })
  const observer = new QueryObserver(client, { queryKey: key ?? ['read', (runs += 1)], queryFn })
  await new Promise<void>((resolve) => {
    const unsubscribe = observer.subscribe((result) => {
      if (result.status === 'error') {
        unsubscribe()
        resolve()
      }
    })
  })
  return queryFn
}

describe('createQueryClient reads', () => {
  it.each([400, 401, 403, 404, 422, 409, 429])('never retries a %i', async (status) => {
    const { client } = setup()
    const queryFn = await runRead(client, () => apiError(status))
    expect(queryFn).toHaveBeenCalledTimes(1)
  })

  it.each([500, 502, 503])('retries a %i once', async (status) => {
    const { client } = setup()
    const queryFn = await runRead(client, () => apiError(status))
    expect(queryFn).toHaveBeenCalledTimes(2)
  })

  it('retries a network failure once', async () => {
    const { client } = setup()
    const queryFn = await runRead(client, () => new TypeError('Failed to fetch'))
    expect(queryFn).toHaveBeenCalledTimes(2)
  })
})

describe('createQueryClient writes', () => {
  it.each([403, 500, 503])('never retries a %i', async (status) => {
    const { client } = setup()
    const mutationFn = vi.fn<() => Promise<never>>(async () => {
      throw apiError(status)
    })
    await client
      .getMutationCache()
      .build(client, { mutationFn })
      .execute(undefined)
      .catch(() => undefined)
    expect(mutationFn).toHaveBeenCalledTimes(1)
  })

  it('never retries a network failure', async () => {
    const { client } = setup()
    const mutationFn = vi.fn<() => Promise<never>>(async () => {
      throw new TypeError('Failed to fetch')
    })
    await client
      .getMutationCache()
      .build(client, { mutationFn })
      .execute(undefined)
      .catch(() => undefined)
    expect(mutationFn).toHaveBeenCalledTimes(1)
  })
})

describe('createQueryClient unauthorized', () => {
  it('calls onUnauthorized once when /me gets a 401', async () => {
    const { client, onUnauthorized } = setup()
    await runRead(client, () => apiError(401), getGetMeQueryKey())
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('calls onUnauthorized when a write gets a 401', async () => {
    const { client, onUnauthorized } = setup()
    await client
      .getMutationCache()
      .build(client, {
        mutationFn: async () => {
          throw apiError(401)
        },
      })
      .execute(undefined)
      .catch(() => undefined)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('does not call onUnauthorized for other failures', async () => {
    const { client, onUnauthorized } = setup()
    await runRead(client, () => apiError(403))
    await runRead(client, () => new TypeError('Failed to fetch'))
    expect(onUnauthorized).not.toHaveBeenCalled()
  })
})
