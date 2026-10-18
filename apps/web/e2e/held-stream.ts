import type { Page } from '@playwright/test'

// STUB: a turn's answer that stays open, so the page can be tested or photographed mid-stream. The
// scripted model finishes in milliseconds, and its one slow scenario ("scripted silence") says
// nothing at all. Playwright's `page.route` can only answer a request whole, so this wraps the
// page's own `fetch` for the next POST to a conversation's turns and answers it with a stream the
// test pushes events into. Everything else, including creating the conversation, goes to the real
// API. The events are the API's own (see src/lib/stream-turn.ts). Used by conversation.spec.ts and
// the capture report.

type TurnEventName =
  | 'turn.started'
  | 'status'
  | 'text.delta'
  | 'text.retracted'
  | 'citation'
  | 'tool.started'
  | 'tool.finished'
  | 'turn.completed'

declare global {
  interface Window {
    __pushTurnEvent?: (event: string, data: unknown) => void
  }
}

/** Takes over the next turn's POST on this page. Returns what pushes events into it. */
export async function holdNextTurnStream(page: Page) {
  await page.evaluate(() => {
    const realFetch = window.fetch.bind(window)
    window.fetch = (input, init) => {
      const url =
        typeof input === 'string' ? input : input instanceof Request ? input.url : String(input)
      const method = (
        init?.method ?? (input instanceof Request ? input.method : 'GET')
      ).toUpperCase()
      if (method !== 'POST' || !/\/assistant\/conversations\/[^/]+\/turns$/.test(url)) {
        return realFetch(input, init)
      }
      window.fetch = realFetch
      const encoder = new TextEncoder()
      let controller!: ReadableStreamDefaultController<Uint8Array>
      const body = new ReadableStream<Uint8Array>({
        start(c) {
          controller = c
        },
      })
      window.__pushTurnEvent = (event, data) => {
        try {
          controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`))
        } catch {
          // The page has canceled the stream (Stop, or a persona switch). A late event goes nowhere.
        }
      }
      return Promise.resolve(
        new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }),
      )
    }
  })
  return {
    async push(event: TurnEventName, data: unknown) {
      await page.waitForFunction(() => window.__pushTurnEvent !== undefined)
      await page.evaluate(([name, payload]) => window.__pushTurnEvent!(name as string, payload), [
        event,
        data,
      ] as const)
    },
  }
}

/** The first passage of §4.3, as a citation event the stream carries. */
export const SICK_LEAVE_CITATION = {
  marker: 1,
  sectionId: '4.3',
  passageId: 'p1',
  title: 'Sick leave',
  groupName: 'Time off',
  audienceLabel: 'Everyone',
  lastUpdated: '2026-10-13',
  deepLink: '/handbook/4.3?passage=p1',
  citedText:
    'Juniper Row gives every employee 40 hours (5 days) of paid sick leave each year. This is the company rule for any state that has no sick leave law of its own, which today includes Texas and Georgia.',
}

/** The words of the first sentence, which the citation's marker follows. */
export const SICK_LEAVE_SENTENCE =
  'Juniper Row gives every employee 40 hours (5 days) of paid sick leave each year.'

/** What the stream carries first: the turn starting, the search, and its result. */
export async function pushSearchSteps(stream: Awaited<ReturnType<typeof holdNextTurnStream>>) {
  await stream.push('turn.started', { turnId: '00000000-0000-4000-8000-000000000001' })
  await stream.push('status', { text: 'Searching the handbook…' })
  await stream.push('tool.started', {
    id: 't1',
    name: 'search_handbook',
    summary: "query='sick leave'",
  })
  await stream.push('tool.finished', { id: 't1', ok: true, summary: 'done', durationMs: 12 })
}
