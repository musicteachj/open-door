import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const setNonce = vi.fn<(value: string) => void>()
vi.mock('get-nonce', () => ({ setNonce: (value: string) => setNonce(value) }))

import { applyNonce, readNonce } from './csp-nonce'

function putMeta(content: string | null) {
  document.head.innerHTML = content === null ? '' : `<meta name="csp-nonce" content="${content}">`
}

describe('readNonce', () => {
  afterEach(() => {
    document.head.innerHTML = ''
  })

  it('returns the meta tag’s value', () => {
    putMeta('abc123')
    expect(readNonce()).toBe('abc123')
  })

  it('returns undefined when the tag is empty (the development page)', () => {
    putMeta('')
    expect(readNonce()).toBeUndefined()
  })

  it('returns undefined when there is no tag', () => {
    putMeta(null)
    expect(readNonce()).toBeUndefined()
  })
})

describe('applyNonce', () => {
  beforeEach(() => {
    setNonce.mockClear()
  })

  afterEach(() => {
    document.head.innerHTML = ''
  })

  it('hands the nonce to get-nonce when the page has one', () => {
    putMeta('abc123')
    applyNonce()
    expect(setNonce).toHaveBeenCalledExactlyOnceWith('abc123')
  })

  it('does nothing in development', () => {
    putMeta('')
    applyNonce()
    expect(setNonce).not.toHaveBeenCalled()
  })
})
