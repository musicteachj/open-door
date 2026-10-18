import { describe, expect, it } from 'vitest'
import { readSse, type SseMessage } from './sse'

const encoder = new TextEncoder()

/** A stream that delivers each chunk (text or raw bytes) as one read. */
function streamOf(...chunks: (string | Uint8Array)[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(typeof chunk === 'string' ? encoder.encode(chunk) : chunk)
      }
      controller.close()
    },
  })
}

async function collect(stream: ReadableStream<Uint8Array>, signal?: AbortSignal) {
  const messages: SseMessage[] = []
  for await (const message of readSse(stream, signal)) messages.push(message)
  return messages
}

describe('readSse', () => {
  it('reads an event and its data', async () => {
    const messages = await collect(streamOf('event: status\ndata: {"text":"Hi"}\n\n'))
    expect(messages).toEqual([{ event: 'status', data: '{"text":"Hi"}' }])
  })

  it('reads several events in one chunk', async () => {
    const messages = await collect(streamOf('event: a\ndata: 1\n\nevent: b\ndata: 2\n\n'))
    expect(messages).toEqual([
      { event: 'a', data: '1' },
      { event: 'b', data: '2' },
    ])
  })

  it('reads an event split across chunks, in the middle of a field', async () => {
    const messages = await collect(
      streamOf('eve', 'nt: sta', 'tus\ndata: {"te', 'xt":"Hi"}\n', '\n'),
    )
    expect(messages).toEqual([{ event: 'status', data: '{"text":"Hi"}' }])
  })

  it('reads an event whose blank-line separator is split across chunks', async () => {
    const messages = await collect(streamOf('event: a\ndata: 1\n', '\nevent: b\ndata: 2\n\n'))
    expect(messages).toEqual([
      { event: 'a', data: '1' },
      { event: 'b', data: '2' },
    ])
  })

  it('reads a multi-byte character split inside its bytes', async () => {
    const bytes = encoder.encode('event: text.delta\ndata: {"text":"café \u{1F600}"}\n\n')
    // Cut inside the two-byte "e with an acute" and inside the four-byte emoji.
    const cutAcute = bytes.indexOf(0xc3) + 1
    const cutEmoji = bytes.indexOf(0xf0) + 2
    const messages = await collect(
      streamOf(bytes.slice(0, cutAcute), bytes.slice(cutAcute, cutEmoji), bytes.slice(cutEmoji)),
    )
    expect(messages).toEqual([{ event: 'text.delta', data: '{"text":"café \u{1F600}"}' }])
  })

  it('reads one byte at a time', async () => {
    const bytes = encoder.encode('event: a\ndata: héllo\n\n: ping\n\nevent: b\ndata: 2\n\n')
    const messages = await collect(streamOf(...Array.from(bytes, (byte) => new Uint8Array([byte]))))
    expect(messages).toEqual([
      { event: 'a', data: 'héllo' },
      { event: 'b', data: '2' },
    ])
  })

  it('reads one long event the same however it is cut into chunks', async () => {
    const text = `${'word '.repeat(2000)}end`
    const wire = `event: text.delta\ndata: ${JSON.stringify({ text })}\n\nevent: b\ndata: 2\n\n`
    const expected = [
      { event: 'text.delta', data: JSON.stringify({ text }) },
      { event: 'b', data: '2' },
    ]
    for (const size of [1, 3, 7, 64, 1000]) {
      const bytes = encoder.encode(wire)
      const chunks: Uint8Array[] = []
      for (let at = 0; at < bytes.length; at += size) chunks.push(bytes.slice(at, at + size))
      expect(await collect(streamOf(...chunks))).toEqual(expected)
    }
  })

  it('finds a line end that falls exactly at the start of a chunk, after a long partial line', async () => {
    const messages = await collect(
      streamOf(
        'event: a\ndata: ',
        'x'.repeat(50),
        'y'.repeat(50),
        '\n',
        '\n',
        'event: b\r',
        '\ndata: 2\r\n\r\n',
      ),
    )
    expect(messages).toEqual([
      { event: 'a', data: `${'x'.repeat(50)}${'y'.repeat(50)}` },
      { event: 'b', data: '2' },
    ])
  })

  it('ignores comments, such as the keep-alive heartbeat', async () => {
    const messages = await collect(
      streamOf(': keep-alive\n\n', 'event: a\ndata: 1\n\n', ': keep-alive\n\n'),
    )
    expect(messages).toEqual([{ event: 'a', data: '1' }])
  })

  it('ignores a comment inside an event', async () => {
    const messages = await collect(streamOf('event: a\n: note\ndata: 1\n\n'))
    expect(messages).toEqual([{ event: 'a', data: '1' }])
  })

  it('joins a multi-line data field with newlines', async () => {
    const messages = await collect(
      streamOf('event: a\ndata: one\ndata: two\ndata:\ndata: four\n\n'),
    )
    expect(messages).toEqual([{ event: 'a', data: 'one\ntwo\n\nfour' }])
  })

  it('reads CRLF line endings, including a CRLF split between chunks', async () => {
    const messages = await collect(
      streamOf('event: a\r\ndata: 1\r\n\r\n', 'event: b\r', '\ndata: 2\r', '\n\r', '\n'),
    )
    expect(messages).toEqual([
      { event: 'a', data: '1' },
      { event: 'b', data: '2' },
    ])
  })

  it('reads bare CR line endings', async () => {
    const messages = await collect(streamOf('event: a\rdata: 1\r\r'))
    expect(messages).toEqual([{ event: 'a', data: '1' }])
  })

  it('strips one leading space from a value, and no more', async () => {
    const messages = await collect(streamOf('event:a\ndata:  two spaces\n\n'))
    expect(messages).toEqual([{ event: 'a', data: ' two spaces' }])
  })

  it('names an event with no event field "message"', async () => {
    const messages = await collect(streamOf('data: 1\n\n'))
    expect(messages).toEqual([{ event: 'message', data: '1' }])
  })

  it('does not carry the event name into the next event', async () => {
    const messages = await collect(streamOf('event: a\ndata: 1\n\ndata: 2\n\n'))
    expect(messages.map((m) => m.event)).toEqual(['a', 'message'])
  })

  it('skips an event with no data', async () => {
    const messages = await collect(streamOf('event: a\n\nevent: b\ndata: 2\n\n'))
    expect(messages).toEqual([{ event: 'b', data: '2' }])
  })

  it('drops an event the stream ended in the middle of', async () => {
    const messages = await collect(streamOf('event: a\ndata: 1\n\nevent: b\ndata: 2'))
    expect(messages).toEqual([{ event: 'a', data: '1' }])
    // The same when its lines were complete but the blank line that ends it never came.
    const unfinished = await collect(streamOf('event: a\ndata: 1\n\nevent: b\ndata: 2\n'))
    expect(unfinished).toEqual([{ event: 'a', data: '1' }])
  })

  it('ignores an unknown field and a line with no colon', async () => {
    const messages = await collect(streamOf('id: 7\nretry: 5\nnonsense\nevent: a\ndata: 1\n\n'))
    expect(messages).toEqual([{ event: 'a', data: '1' }])
  })

  it('stops reading when the signal aborts, and cancels the stream', async () => {
    let canceled = false
    let controller!: ReadableStreamDefaultController<Uint8Array>
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        controller = c
      },
      cancel() {
        canceled = true
      },
    })
    const abort = new AbortController()
    controller.enqueue(encoder.encode('event: a\ndata: 1\n\n'))
    const seen: SseMessage[] = []
    const reading = (async () => {
      for await (const message of readSse(stream, abort.signal)) seen.push(message)
    })()
    await new Promise((resolve) => setTimeout(resolve, 10))
    abort.abort()
    await reading
    expect(seen).toEqual([{ event: 'a', data: '1' }])
    expect(canceled).toBe(true)
  })

  it('reads nothing from a signal that is already aborted', async () => {
    const abort = new AbortController()
    abort.abort()
    const messages = await collect(streamOf('event: a\ndata: 1\n\n'), abort.signal)
    expect(messages).toEqual([])
  })
})
