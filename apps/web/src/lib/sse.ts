// A server-sent events parser over a response body. The browser's EventSource cannot send a POST
// body or a CSRF header, so the turn stream reads the body itself. It follows the WHATWG
// "Server-sent events" parsing rules for what the API sends: `event:` and `data:` fields, blank
// lines that end an event, and `:` comment lines (the heartbeat).

export type SseMessage = {
  /** The `event:` field, or "message" when the event had none. */
  event: string
  /** The `data:` lines joined with newlines. */
  data: string
}

/**
 * Reads server-sent events from `stream` until it ends or `signal` aborts (which also cancels the
 * stream). An event the stream ended in the middle of is dropped, as the standard says, and so is
 * an event with no data field.
 */
export async function* readSse(
  stream: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<SseMessage, void, undefined> {
  const reader = stream.getReader()
  // Decoding with `{ stream: true }` keeps the bytes of a character split across two reads until the rest arrives.
  const decoder = new TextDecoder()
  const stop = () => void reader.cancel().catch(() => {})
  if (signal?.aborted) {
    stop()
    return
  }
  signal?.addEventListener('abort', stop, { once: true })

  let buffer = ''
  // How much of `buffer` has been looked at already. A line that is still arriving is not
  // rescanned from its start on every read, so a long event costs time in proportion to its size.
  let scanned = 0
  // A chunk can end on "\r", and the next can start with the "\n" of the same CRLF.
  let skipLineFeed = false
  let eventName = ''
  let dataLines: string[] = []

  try {
    for (;;) {
      let read: ReadableStreamReadResult<Uint8Array>
      try {
        read = await reader.read()
      } catch (error) {
        if (signal?.aborted) return
        throw error
      }
      if (read.done) return
      buffer += decoder.decode(read.value, { stream: true })

      let start = 0
      for (let i = scanned; i < buffer.length; i++) {
        const char = buffer[i]
        if (skipLineFeed) {
          skipLineFeed = false
          if (char === '\n') {
            start = i + 1
            continue
          }
        }
        if (char !== '\n' && char !== '\r') continue
        const line = buffer.slice(start, i)
        start = i + 1
        if (char === '\r') {
          if (buffer[i + 1] === '\n') {
            i++
            start = i + 1
          } else if (i + 1 === buffer.length) {
            skipLineFeed = true
          }
        }

        if (line === '') {
          // A blank line ends the event.
          if (dataLines.length > 0) {
            const message = {
              event: eventName === '' ? 'message' : eventName,
              data: dataLines.join('\n'),
            }
            eventName = ''
            dataLines = []
            if (signal?.aborted) return
            yield message
          }
          eventName = ''
          dataLines = []
          continue
        }
        if (line.startsWith(':')) continue

        const colon = line.indexOf(':')
        const field = colon === -1 ? line : line.slice(0, colon)
        let value = colon === -1 ? '' : line.slice(colon + 1)
        if (value.startsWith(' ')) value = value.slice(1)
        if (field === 'event') eventName = value
        else if (field === 'data') dataLines.push(value)
        // Any other field (id, retry) is not used.
      }
      buffer = buffer.slice(start)
      scanned = buffer.length
    }
  } finally {
    signal?.removeEventListener('abort', stop)
    // A reader who stops early (or a stream that has ended) leaves nothing open behind.
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
