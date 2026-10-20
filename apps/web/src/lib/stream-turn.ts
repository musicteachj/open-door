import type { CitationOut, EscalationOut } from '@/api/generated'
import { ApiError, applyCsrfHeader, apiErrorFrom } from './api-fetch'
import { readSse } from './sse'

// The one hand-written API call besides `apiFetch`: the generated client reads a whole body, and a
// turn is a stream. It shares `apiFetch`'s CSRF rule and its error type, so a refusal before the
// stream (a 409, a 422, a 429) is the same `ApiError` as anywhere else.

/** The `escalation` event: `EscalationOut` plus whether the page may offer to open a case. */
export type EscalationEvent = EscalationOut & { offerCase: boolean }

/** The `error` event. `code` is one of the API's codes, or one this version does not know. */
export type TurnErrorEvent = {
  code: string
  message: string
  requestId: string | null
}

/** Every event a turn's stream sends, named by `type` (the SSE `event:` field) and carrying `data`. */
export type TurnStreamEvent =
  | { type: 'turn.started'; data: { turnId: string } }
  | { type: 'status'; data: { text: string } }
  | { type: 'text.delta'; data: { text: string } }
  /** Drop all answer text and citations shown so far. The note follows as a `status` event. */
  | { type: 'text.retracted'; data: Record<string, never> }
  | { type: 'citation'; data: CitationOut }
  | { type: 'tool.started'; data: { id: string; name: string; summary: string } }
  | {
      type: 'tool.finished'
      data: { id: string; ok: boolean; summary: string; durationMs: number }
    }
  | { type: 'escalation'; data: EscalationEvent }
  | { type: 'error'; data: TurnErrorEvent }
  | {
      type: 'turn.completed'
      data: {
        turnId: string
        servedBy: string
        usage: { inputTokens: number; outputTokens: number }
        /** Present (true) only when the output limit cut the answer off. */
        incomplete?: boolean
      }
    }

const EVENT_NAMES: ReadonlySet<string> = new Set<TurnStreamEvent['type']>([
  'turn.started',
  'status',
  'text.delta',
  'text.retracted',
  'citation',
  'tool.started',
  'tool.finished',
  'escalation',
  'error',
  'turn.completed',
])

function isEventName(name: string): name is TurnStreamEvent['type'] {
  return EVENT_NAMES.has(name)
}

export function turnsUrl(conversationId: string): string {
  return `/api/v1/assistant/conversations/${conversationId}/turns`
}

type StreamTurnOptions = {
  /** Aborting stops reading and closes the connection, which the server saves as "stopped". */
  signal?: AbortSignal
  onEvent: (event: TurnStreamEvent) => void
  /**
   * Called once when the server has answered with a stream (status 200, before any event). From
   * then on the server has the turn, whatever happens to the connection.
   */
  onResponse?: () => void
}

/**
 * Asks a question and hands over the turn's events as they arrive. It resolves when the stream
 * ends or the signal aborts (a stop is not an error), and rejects with an `ApiError` when the
 * server refuses before streaming, or with the network's own error. Names it does not know, and
 * events whose data is not a JSON object, are ignored.
 */
export async function streamTurn(
  conversationId: string,
  question: string,
  { signal, onEvent, onResponse }: StreamTurnOptions,
): Promise<void> {
  if (signal?.aborted) return
  const url = turnsUrl(conversationId)
  const headers = new Headers({ 'Content-Type': 'application/json', Accept: 'text/event-stream' })
  applyCsrfHeader(headers, 'POST', url)

  let response: Response
  try {
    response = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify({ question }),
      credentials: 'same-origin',
      signal,
    })
  } catch (error) {
    if (signal?.aborted) return
    throw error
  }
  if (!response.ok) throw apiErrorFrom(response, await response.text())
  // A 2xx that is not a stream, such as an HTML page from a misconfigured proxy, is a failed send:
  // the server did not take the question, so nothing is "accepted" and the draft stays.
  if (!(response.headers.get('Content-Type') ?? '').toLowerCase().includes('text/event-stream')) {
    // Let go of the body so the connection is not held open.
    void response.body?.cancel().catch(() => {})
    throw new ApiError(response.status, null, response.headers.get('X-Request-ID'))
  }
  onResponse?.()
  if (response.body === null) return

  for await (const message of readSse(response.body, signal)) {
    if (signal?.aborted) return
    if (!isEventName(message.event)) continue
    let data: unknown
    try {
      data = JSON.parse(message.data)
    } catch {
      continue
    }
    if (typeof data !== 'object' || data === null) continue
    onEvent({ type: message.event, data } as TurnStreamEvent)
  }
}
