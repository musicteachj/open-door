import { describe, expect, it } from 'vitest'
import type { Problem } from '@/api/generated'
import { ApiError } from '@/lib/api-fetch'
import { SANDBOX_START_FAILED, sandboxStartError } from './sandbox-copy'

const failure = (status: number, type: string, detail?: string) =>
  new ApiError(status, { type, title: 'x', status, instance: '/', detail } as Problem, null)

describe('sandboxStartError', () => {
  it.each([
    ['turnstile-failed', true],
    ['turnstile-unavailable', true],
    ['sandbox-start-limit', false],
    ['sandbox-day-limit', false],
  ])('says the API text for %s (Retry: %s)', (type, canRetry) => {
    expect(sandboxStartError(failure(429, type, 'Its words.'))).toEqual({
      message: 'Its words.',
      canRetry,
    })
  })

  it.each([
    ['another problem type', failure(500, 'about:blank', 'Boom')],
    ['a refusal without text', failure(429, 'sandbox-day-limit')],
    ['no problem body', new ApiError(502, null, null)],
    ['something that is not an API error', new Error('offline')],
    ['no error at all', null],
  ])('keeps the plain text with Retry for %s', (_name, error) => {
    expect(sandboxStartError(error)).toEqual({ message: SANDBOX_START_FAILED, canRetry: true })
  })
})
