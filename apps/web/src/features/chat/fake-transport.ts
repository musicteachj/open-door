import type { ChatTransport } from './transport'

/** The spec's fixed reply (Phase 2 spec, "Assistant home"), for the owner's approval. */
export const FAKE_REPLY =
  "The assistant isn't connected yet. When it is, it will answer here and cite the Juniper Row handbook for every policy it mentions."

type FakeTransportOptions = {
  /** How long the fake waits before it answers. */
  delayMs?: number
  /** Rejects instead of replying, to show the error state. */
  fail?: boolean
}

function abortError(): Error {
  return new DOMException('The send was canceled.', 'AbortError')
}

export function createFakeTransport({
  delayMs = 400,
  fail = false,
}: FakeTransportOptions = {}): ChatTransport {
  return {
    send(_question, { signal }) {
      return new Promise((resolve, reject) => {
        if (signal.aborted) {
          reject(abortError())
          return
        }
        const onAbort = () => {
          clearTimeout(timer)
          reject(abortError())
        }
        const timer = setTimeout(() => {
          signal.removeEventListener('abort', onAbort)
          if (fail) reject(new Error('The fake transport was told to fail.'))
          else resolve({ text: FAKE_REPLY })
        }, delayMs)
        signal.addEventListener('abort', onAbort, { once: true })
      })
    },
  }
}
