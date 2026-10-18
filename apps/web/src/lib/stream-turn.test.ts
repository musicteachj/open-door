import { delay, http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { stubAbsoluteUrls } from '@/test/absolute-urls'
import { server } from '@/test/msw'
import { ApiError } from './api-fetch'
import { streamTurn, type TurnStreamEvent } from './stream-turn'

const CONVERSATION = 'c0ffee00-0000-4000-8000-000000000001'
const TURN = 'c0ffee00-0000-4000-8000-0000000000aa'
const url = (path: string) => `${window.location.origin}${path}`
const TURNS_URL = url(`/api/v1/assistant/conversations/${CONVERSATION}/turns`)

const encoder = new TextEncoder()

function sse(event: string, data: unknown) {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

function streamResponse(...chunks: string[]) {
  return new HttpResponse(
    new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
        controller.close()
      },
    }),
    { headers: { 'Content-Type': 'text/event-stream' } },
  )
}

async function run(
  question = 'How many sick days do I get?',
  signal?: AbortSignal,
): Promise<TurnStreamEvent[]> {
  const events: TurnStreamEvent[] = []
  await streamTurn(CONVERSATION, question, { signal, onEvent: (event) => events.push(event) })
  return events
}

function setCsrf(value: string) {
  document.cookie = `__Host-od_csrf=${value}; Secure; Path=/`
}

beforeEach(() => {
  stubAbsoluteUrls()
})

afterEach(() => {
  for (const part of document.cookie.split('; ')) {
    const name = part.split('=')[0]
    if (name) document.cookie = `${name}=; Secure; Path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`
  }
})

describe('streamTurn: the request', () => {
  it('posts the question as JSON with the CSRF token, same-origin', async () => {
    setCsrf('token-9')
    let seen: {
      body: unknown
      csrf: string | null
      type: string | null
      credentials: string
    } | null = null
    server.use(
      http.post(TURNS_URL, async ({ request }) => {
        seen = {
          body: await request.json(),
          csrf: request.headers.get('X-CSRF-Token'),
          type: request.headers.get('Content-Type'),
          credentials: request.credentials,
        }
        return streamResponse(sse('turn.started', { turnId: TURN }))
      }),
    )
    await run('Hello there')
    expect(seen).toEqual({
      body: { question: 'Hello there' },
      csrf: 'token-9',
      type: 'application/json',
      credentials: 'same-origin',
    })
  })

  it('sends no token when there is no cookie', async () => {
    let csrf: string | null = 'unset'
    server.use(
      http.post(TURNS_URL, ({ request }) => {
        csrf = request.headers.get('X-CSRF-Token')
        return streamResponse()
      }),
    )
    await run()
    expect(csrf).toBeNull()
  })
})

describe('streamTurn: the events', () => {
  it('hands over every event, typed and in order', async () => {
    const citation = {
      marker: 1,
      offsetUtf16: 12,
      sectionId: 'CA-4.3',
      passageId: 'CA-4.3~p1',
      title: 'Sick leave',
      groupName: 'California addendum',
      audienceLabel: 'California employees',
      lastUpdated: '2026-09-12',
      deepLink: '/handbook/CA-4.3?passage=CA-4.3~p1',
      citedText: 'Employees accrue paid sick leave.',
    }
    const contact = {
      name: 'Dana Whitfield',
      workEmail: 'dana@juniperrow.example',
      jobTitle: 'HR Business Partner',
      locationName: 'Denver HQ',
    }
    server.use(
      http.post(TURNS_URL, () =>
        streamResponse(
          sse('turn.started', { turnId: TURN }),
          ': keep-alive\n\n',
          sse('status', { text: 'Searching the handbook' }),
          sse('tool.started', { id: 't1', name: 'search_handbook', summary: "query='sick leave'" }),
          sse('tool.finished', { id: 't1', ok: true, summary: '3 results', durationMs: 120 }),
          sse('text.delta', { text: 'You get ' }),
          sse('text.retracted', {}),
          sse('text.delta', { text: '5 days.' }),
          sse('citation', citation),
          sse('escalation', {
            kind: 'sensitive',
            message: 'A person handles this.',
            hrContact: [contact],
            offerCase: false,
          }),
          sse('error', { code: 'internal', message: 'Something went wrong.', requestId: 'r1' }),
          sse('turn.completed', {
            turnId: TURN,
            servedBy: 'anthropic',
            usage: { inputTokens: 10, outputTokens: 5 },
          }),
        ),
      ),
    )
    const events = await run()
    expect(events.map((event) => event.type)).toEqual([
      'turn.started',
      'status',
      'tool.started',
      'tool.finished',
      'text.delta',
      'text.retracted',
      'text.delta',
      'citation',
      'escalation',
      'error',
      'turn.completed',
    ])
    expect(events[0]).toEqual({ type: 'turn.started', data: { turnId: TURN } })
    expect(events[2]).toEqual({
      type: 'tool.started',
      data: { id: 't1', name: 'search_handbook', summary: "query='sick leave'" },
    })
    expect(events[7]).toEqual({ type: 'citation', data: citation })
    const escalation = events[8]
    expect(escalation?.type === 'escalation' && escalation.data.hrContact).toEqual([contact])
    const error = events[9]
    expect(error?.type === 'error' && error.data.code).toBe('internal')
  })

  it('reads an event split across chunks', async () => {
    server.use(
      http.post(TURNS_URL, () =>
        streamResponse('event: text.del', 'ta\ndata: {"text":"Five', ' days"}\n', '\n'),
      ),
    )
    expect(await run()).toEqual([{ type: 'text.delta', data: { text: 'Five days' } }])
  })

  it('ignores an event name it does not know, and one whose data is not JSON', async () => {
    server.use(
      http.post(TURNS_URL, () =>
        streamResponse(
          sse('something.new', { a: 1 }),
          'event: status\ndata: not json\n\n',
          'event: status\ndata: 7\n\n',
          sse('status', { text: 'Still going' }),
        ),
      ),
    )
    expect(await run()).toEqual([{ type: 'status', data: { text: 'Still going' } }])
  })

  it.each([
    'refusal',
    'model-unavailable',
    'budget-sandbox',
    'budget-daily',
    'spend-limit',
    'too-many-calls',
    'internal',
  ])('passes the error code %s through', async (code) => {
    server.use(
      http.post(TURNS_URL, () =>
        streamResponse(sse('error', { code, message: 'Words.', requestId: null })),
      ),
    )
    expect(await run()).toEqual([
      { type: 'error', data: { code, message: 'Words.', requestId: null } },
    ])
  })
})

describe('streamTurn: stopping', () => {
  it('stops reading when the signal aborts, even if the stream never ends, without throwing', async () => {
    server.use(
      http.post(TURNS_URL, () => {
        // One event, then silence: the stream stays open, as a turn that is still thinking does.
        return new HttpResponse(
          new ReadableStream<Uint8Array>({
            start(controller) {
              controller.enqueue(encoder.encode(sse('text.delta', { text: 'One ' })))
            },
          }),
          { headers: { 'Content-Type': 'text/event-stream' } },
        )
      }),
    )
    const abort = new AbortController()
    const events: TurnStreamEvent[] = []
    const running = streamTurn(CONVERSATION, 'Q', {
      signal: abort.signal,
      onEvent: (event) => {
        events.push(event)
        abort.abort()
      },
    })
    await expect(running).resolves.toBeUndefined()
    expect(events).toEqual([{ type: 'text.delta', data: { text: 'One ' } }])
  })

  it('hands over nothing after the signal aborts', async () => {
    server.use(
      http.post(TURNS_URL, () =>
        streamResponse(sse('text.delta', { text: 'a' }), sse('text.delta', { text: 'b' })),
      ),
    )
    const abort = new AbortController()
    const events: TurnStreamEvent[] = []
    await streamTurn(CONVERSATION, 'Q', {
      signal: abort.signal,
      onEvent: (event) => {
        events.push(event)
        abort.abort()
      },
    })
    expect(events).toHaveLength(1)
  })

  it('resolves without throwing when the signal aborts before the server answers', async () => {
    server.use(
      http.post(TURNS_URL, async () => {
        await delay('infinite')
        return streamResponse()
      }),
    )
    const abort = new AbortController()
    const running = run('Q', abort.signal)
    setTimeout(() => abort.abort(), 10)
    expect(await running).toEqual([])
  })

  it('resolves without a request when the signal is already aborted', async () => {
    let called = false
    server.use(
      http.post(TURNS_URL, () => {
        called = true
        return streamResponse()
      }),
    )
    const abort = new AbortController()
    abort.abort()
    expect(await run('Q', abort.signal)).toEqual([])
    expect(called).toBe(false)
  })
})

describe('streamTurn: a response that is not a stream', () => {
  it('throws an ApiError with the problem, its code, and the request id', async () => {
    server.use(
      http.post(TURNS_URL, () =>
        HttpResponse.json(
          {
            type: 'turn-running',
            title: 'Still answering',
            status: 409,
            instance: '/x',
            detail: 'Wait for it.',
          },
          {
            status: 409,
            headers: { 'X-Request-ID': 'req-77', 'Content-Type': 'application/problem+json' },
          },
        ),
      ),
    )
    const error = await run().catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(ApiError)
    const apiError = error as ApiError
    expect(apiError.status).toBe(409)
    expect(apiError.problem?.type).toBe('turn-running')
    expect(apiError.problem?.detail).toBe('Wait for it.')
    expect(apiError.requestId).toBe('req-77')
  })

  it('throws an ApiError with no problem when the body is not one', async () => {
    server.use(
      http.post(TURNS_URL, () => new HttpResponse('<html>Bad gateway</html>', { status: 502 })),
    )
    const error = (await run().catch((caught: unknown) => caught)) as ApiError
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(502)
    expect(error.problem).toBeNull()
  })

  it('lets a network failure through as it is', async () => {
    server.use(http.post(TURNS_URL, () => HttpResponse.error()))
    await expect(run()).rejects.toThrow(TypeError)
  })
})
