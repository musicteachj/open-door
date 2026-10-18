import { QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { delay, http, HttpResponse } from 'msw'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getGetCurrentConversationQueryKey, useGetMe, type CitationOut } from '@/api/generated'
import { resetIdentity } from '@/lib/identity'
import { createQueryClient } from '@/lib/query-client'
import { citation } from '@/test/assistant-fixtures'
import { stubAbsoluteUrls } from '@/test/absolute-urls'
import {
  CONVERSATION_ID,
  TEXTS,
  TURN_ID,
  conversationOut,
  eventStream,
  installAssistantApi,
  onFeedback,
  onTurn,
  openStream,
  problemResponse,
  turnOut,
} from '@/test/fake-assistant'
import { meFor } from '@/test/fixtures'
import { server } from '@/test/msw'
import { useChatStore } from './store'
import {
  useAssistantTexts,
  useBudgetBeforeConversation,
  useConversationActions,
  useConversationTurns,
  createRunningPoller,
  useCurrentConversation,
  useFeedback,
} from './use-conversation'

const url = (path: string) => `${window.location.origin}${path}`

function setup() {
  const queryClient = createQueryClient({ onUnauthorized: vi.fn<() => void>(), retryDelayMs: 0 })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return { queryClient, wrapper }
}

const started = ['turn.started', { turnId: TURN_ID }] as [string, unknown]
const completed = [
  'turn.completed',
  { turnId: TURN_ID, servedBy: 'anthropic', usage: { inputTokens: 1, outputTokens: 1 } },
] as [string, unknown]

beforeEach(() => {
  stubAbsoluteUrls()
  useChatStore.setState(useChatStore.getInitialState())
})
afterEach(() => {
  const { queryClient } = setup()
  resetIdentity(queryClient)
})

describe('useCurrentConversation', () => {
  it("numbers each turn's citations by section, once per fetch", async () => {
    const raw: CitationOut[] = [
      citation({ marker: 1, passageId: 'CA-4.3~p1', offsetUtf16: 10 }),
      citation({ marker: 2, passageId: 'CA-4.3~p2', offsetUtf16: 30 }),
      citation({ marker: 3, sectionId: '4.3', passageId: '4.3~p3', offsetUtf16: 50 }),
    ]
    installAssistantApi({ conversation: conversationOut({ turns: [turnOut({ citations: raw })] }) })
    const { wrapper } = setup()
    const { result, rerender } = renderHook(() => useCurrentConversation(), { wrapper })
    await waitFor(() => expect(result.current.data).toBeDefined())
    const first = result.current.data
    expect(first?.turns[0]?.citations.map((c) => c.marker)).toEqual([1, 1, 2])
    rerender()
    expect(result.current.data).toBe(first)
  })

  it('is null before the first question', async () => {
    installAssistantApi()
    const { wrapper } = setup()
    const { result } = renderHook(() => useCurrentConversation(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toBeNull()
  })
})

describe('a first question that creates the conversation', () => {
  // (The creation in flight is module state, so a test must not leave one behind.)
  it('does not create a second conversation when Stop and a new question come while the first is still being created', async () => {
    installAssistantApi()
    let creations = 0
    server.use(
      http.post(url('/api/v1/assistant/conversations'), async () => {
        creations++
        await delay(150)
        return HttpResponse.json(conversationOut({ id: `made-${creations}` }), { status: 201 })
      }),
    )
    const posted = onTurn(() => eventStream(started, completed))
    const { wrapper } = setup()
    const { result } = renderHook(() => useConversationActions(), { wrapper })
    await waitFor(() => expect(result.current.ready).toBe(true))

    const first = result.current.send('First')
    await waitFor(() => expect(creations).toBe(1))
    act(() => result.current.stop())
    const second = result.current.send('Second')
    await act(async () => {
      await Promise.all([first, second])
    })

    expect(creations).toBe(1)
    expect(posted.map((p) => p.conversationId)).toEqual(['made-1'])
  })

  it('shares the creation across a remount: the home and the conversation are different components', async () => {
    installAssistantApi()
    let creations = 0
    server.use(
      http.post(url('/api/v1/assistant/conversations'), async () => {
        creations++
        await delay(150)
        return HttpResponse.json(conversationOut({ id: `made-${creations}` }), { status: 201 })
      }),
    )
    const posted = onTurn(() => eventStream(started, completed))
    const { wrapper } = setup()
    const home = renderHook(() => useConversationActions(), { wrapper })
    await waitFor(() => expect(home.result.current.ready).toBe(true))
    const first = home.result.current.send('First')
    await waitFor(() => expect(creations).toBe(1))
    act(() => home.result.current.stop())
    // The page changes shape: the home goes, and the conversation takes its place.
    home.unmount()
    const conversation = renderHook(() => useConversationActions(), { wrapper })
    await waitFor(() => expect(conversation.result.current.ready).toBe(true))
    const second = conversation.result.current.send('Second')
    await act(async () => {
      await Promise.all([first, second])
    })

    expect(creations).toBe(1)
    expect(posted.map((p) => p.conversationId)).toEqual(['made-1'])
  })

  it('forgets a creation still on its way when the person changes', async () => {
    installAssistantApi()
    let creations = 0
    server.use(
      http.post(url('/api/v1/assistant/conversations'), async () => {
        creations++
        await delay(600)
        return HttpResponse.json(conversationOut({ id: `made-${creations}` }), { status: 201 })
      }),
    )
    onTurn(() => eventStream(started, completed))
    const { wrapper, queryClient } = setup()
    const { result } = renderHook(() => useConversationActions(), { wrapper })
    await waitFor(() => expect(result.current.ready).toBe(true))
    const first = result.current.send('First')
    await waitFor(() => expect(creations).toBe(1))
    // Someone else signs in: their first question must not wait for, or use, the earlier creation.
    act(() => resetIdentity(queryClient))
    const next = renderHook(() => useConversationActions(), { wrapper })
    await waitFor(() => expect(next.result.current.ready).toBe(true))
    await act(async () => {
      await Promise.all([first, next.result.current.send('Theirs')])
    })
    expect(creations).toBe(2)
  })

  it('creates again for a question asked after the creation is over and failed', async () => {
    installAssistantApi()
    let creations = 0
    server.use(
      http.post(url('/api/v1/assistant/conversations'), () => {
        creations++
        return creations === 1
          ? new HttpResponse(null, { status: 500 })
          : HttpResponse.json(conversationOut({ id: 'made-2' }), { status: 201 })
      }),
    )
    onTurn(() => eventStream(started, completed))
    const { wrapper } = setup()
    const { result } = renderHook(() => useConversationActions(), { wrapper })
    await waitFor(() => expect(result.current.ready).toBe(true))
    await act(() => result.current.send('First'))
    await act(() => result.current.send('Second'))
    expect(creations).toBe(2)
  })
})

describe('a send that cannot find out whether there is a conversation', () => {
  it('shows the failed-send message and keeps the draft, without an unhandled rejection', async () => {
    installAssistantApi()
    server.use(
      http.get(
        url('/api/v1/assistant/conversations/current'),
        () => new HttpResponse(null, { status: 500 }),
      ),
    )
    const posted = onTurn(() => eventStream(started, completed))
    const { wrapper } = setup()
    const { result } = renderHook(() => useConversationActions(), { wrapper })
    await waitFor(() => expect(result.current.ready).toBe(true))
    useChatStore.getState().setDraft('Hello')

    // The composer calls `void send(...)`: a rejection here would be nobody's to catch.
    await act(() => result.current.send('Hello'))

    expect(useChatStore.getState().sendError).toBe('Something went wrong sending that.')
    expect(useChatStore.getState().draft).toBe('Hello')
    expect(useChatStore.getState().status).toBe('idle')
    expect(posted).toHaveLength(0)
  })

  it('lets the next send try again', async () => {
    installAssistantApi()
    let calls = 0
    server.use(
      http.get(url('/api/v1/assistant/conversations/current'), () =>
        ++calls <= 2 ? new HttpResponse(null, { status: 500 }) : HttpResponse.json(null),
      ),
    )
    const posted = onTurn(() => eventStream(started, completed))
    const { wrapper } = setup()
    const { result } = renderHook(() => useConversationActions(), { wrapper })
    await waitFor(() => expect(result.current.ready).toBe(true))
    await act(() => result.current.send('Hello'))
    expect(posted).toHaveLength(0)
    await act(() => result.current.send('Hello'))
    expect(posted).toHaveLength(1)
  })
})

describe('a conversation that is gone', () => {
  it('sends the next question to the conversation the server has now, not the dead one still in the cache', async () => {
    const api = installAssistantApi({ conversation: conversationOut({ id: 'gone-1' }) })
    const posted = onTurn((_question, conversationId) =>
      conversationId === 'gone-1'
        ? problemResponse(404, 'about:blank', 'Not found')
        : eventStream(started, completed),
    )
    const { wrapper } = setup()
    const { result } = renderHook(
      () => ({ actions: useConversationActions(), view: useConversationTurns() }),
      {
        wrapper,
      },
    )
    await waitFor(() => expect(result.current.view.conversation.data?.id).toBe('gone-1'))
    await waitFor(() => expect(result.current.actions.ready).toBe(true))

    // The server's current conversation is another one by the time the 404 comes back.
    api.setCurrent(conversationOut({ id: 'live-2' }))
    // ... and the read that says so is slow, so the next question goes out before it lands.
    server.use(
      http.get(url('/api/v1/assistant/conversations/current'), async () => {
        await delay(300)
        return HttpResponse.json(conversationOut({ id: 'live-2' }))
      }),
    )
    await act(() => result.current.actions.send('First'))
    await act(() => result.current.actions.send('Second'))

    expect(posted.map((p) => p.conversationId)).toEqual(['gone-1', 'live-2'])
  })
})

describe('the budget before a conversation', () => {
  it('is read while there is no conversation, and again when the conversation is read again', async () => {
    const api = installAssistantApi()
    const { wrapper, queryClient } = setup()
    const { result } = renderHook(() => useBudgetBeforeConversation(false), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.requests.budget).toBe(1)
    // A refused send, a new conversation: the conversation is read again, and the budget with it.
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: getGetCurrentConversationQueryKey() })
    })
    expect(api.requests.budget).toBe(1)
    const actions = renderHook(() => useConversationActions(), { wrapper })
    await waitFor(() => expect(actions.result.current.ready).toBe(true))
    await act(() => actions.result.current.startNewConversation())
    await waitFor(() => expect(api.requests.budget).toBe(2))
  })

  it('is not read once there is a conversation, which carries its own', async () => {
    const api = installAssistantApi({ conversation: conversationOut() })
    const { wrapper } = setup()
    const { result } = renderHook(() => useBudgetBeforeConversation(true), { wrapper })
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(result.current.fetchStatus).toBe('idle')
    expect(api.requests.budget).toBe(0)
  })

  it('is not read before it is known whether there is a conversation', async () => {
    const api = installAssistantApi()
    const { wrapper } = setup()
    renderHook(() => useBudgetBeforeConversation(undefined), { wrapper })
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(api.requests.budget).toBe(0)
  })
})

describe('useAssistantTexts', () => {
  it('fetches the texts once and keeps them, however often a page mounts', async () => {
    const api = installAssistantApi()
    const { wrapper } = setup()
    const first = renderHook(() => useAssistantTexts(), { wrapper })
    await waitFor(() => expect(first.result.current.data).toEqual(TEXTS))
    first.unmount()
    const second = renderHook(() => useAssistantTexts(), { wrapper })
    expect(second.result.current.data).toEqual(TEXTS)
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(api.requests.texts).toBe(1)
  })
})

describe('sending through the hooks', () => {
  function useAll() {
    return {
      conversation: useCurrentConversation(),
      actions: useConversationActions(),
      view: useConversationTurns(),
    }
  }

  it('creates the conversation for the first question, and reuses it for the next', async () => {
    const api = installAssistantApi()
    // The read has not caught up with the new conversation: it still says there is none.
    server.use(
      http.get(url('/api/v1/assistant/conversations/current'), () => HttpResponse.json(null)),
    )
    const posted = onTurn(() => eventStream(started, completed))
    const { wrapper } = setup()
    const { result } = renderHook(useAll, { wrapper })
    await waitFor(() => expect(result.current.actions.ready).toBe(true))
    await waitFor(() => expect(result.current.conversation.isSuccess).toBe(true))

    await act(() => result.current.actions.send('First'))
    await act(() => result.current.actions.send('Second'))

    expect(api.requests.created).toBe(1)
    expect(posted.map((p) => p.conversationId)).toEqual([CONVERSATION_ID, CONVERSATION_ID])
  })

  it('asks in the conversation the page shows', async () => {
    const api = installAssistantApi({ conversation: conversationOut({ id: 'existing-1' }) })
    const posted = onTurn(() => eventStream(started, completed))
    const { wrapper } = setup()
    const { result } = renderHook(useAll, { wrapper })
    await waitFor(() => expect(result.current.conversation.data?.id).toBe('existing-1'))
    await act(() => result.current.actions.send('Hello'))
    expect(api.requests.created).toBe(0)
    expect(posted[0]?.conversationId).toBe('existing-1')
  })

  it('refetches the conversation on turn.completed, and ends the live turn only once the refetch holds it', async () => {
    const api = installAssistantApi({ conversation: conversationOut() })
    onTurn(() => eventStream(started, ['text.delta', { text: 'You get 5 days.' }], completed))
    const { wrapper } = setup()
    const { result } = renderHook(useAll, { wrapper })
    await waitFor(() => expect(result.current.conversation.isSuccess).toBe(true))
    const before = api.requests.current

    await act(() => result.current.actions.send('Sick days?'))
    // Invalidated, so it was asked for again.
    await waitFor(() => expect(api.requests.current).toBeGreaterThan(before))
    // The refetch does not hold the turn yet: the live turn stays, and shows.
    expect(useChatStore.getState().turn).toMatchObject({ completed: true, text: 'You get 5 days.' })
    expect(result.current.view.live?.text).toBe('You get 5 days.')

    // The server's copy arrives with the next read.
    api.setCurrent(conversationOut({ turns: [turnOut({ id: TURN_ID, status: 'completed' })] }))
    await act(async () => {
      await result.current.conversation.refetch()
    })
    await waitFor(() => expect(useChatStore.getState().turn).toBeNull())
    expect(result.current.view.live).toBeNull()
    expect(result.current.view.turns.map((t) => t.id)).toEqual([TURN_ID])
  })

  it('does not end the live turn for a stored copy that is still running', async () => {
    const api = installAssistantApi({ conversation: conversationOut() })
    onTurn(() => eventStream(started, completed))
    const { wrapper } = setup()
    const { result } = renderHook(useAll, { wrapper })
    await waitFor(() => expect(result.current.conversation.isSuccess).toBe(true))
    await waitFor(() => expect(result.current.actions.ready).toBe(true))
    await act(() => result.current.actions.send('Sick days?'))
    api.setCurrent(conversationOut({ turns: [turnOut({ id: TURN_ID, status: 'running' })] }))
    await act(async () => {
      await result.current.conversation.refetch()
    })
    await waitFor(() => expect(result.current.conversation.data?.turns).toHaveLength(1))
    // Give the effect that would end the live turn every chance to run.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    expect(useChatStore.getState().turn).not.toBeNull()
  })

  it('leaves the live turn out of the stored turns, so it is never drawn twice', async () => {
    const stream = openStream()
    installAssistantApi({
      conversation: conversationOut({
        turns: [turnOut({ id: 'old-1' }), turnOut({ id: TURN_ID })],
      }),
    })
    onTurn(() => stream.response())
    const { wrapper } = setup()
    const { result } = renderHook(useAll, { wrapper })
    await waitFor(() => expect(result.current.view.turns).toHaveLength(2))
    const sending = result.current.actions.send('Again')
    stream.push(...started)
    await waitFor(() => expect(result.current.view.live?.turnId).toBe(TURN_ID))
    expect(result.current.view.turns.map((t) => t.id)).toEqual(['old-1'])
    stream.close()
    await act(() => sending)
  })

  it("sends nothing until the API's texts have loaded", async () => {
    installAssistantApi()
    server.use(
      http.get(url('/api/v1/assistant/texts'), async () => {
        await delay('infinite')
        return HttpResponse.json(TEXTS)
      }),
    )
    const posted = onTurn(() => eventStream(started, completed))
    const { wrapper } = setup()
    const { result } = renderHook(useAll, { wrapper })
    expect(result.current.actions.ready).toBe(false)
    await act(() => result.current.actions.send('Hello'))
    expect(posted).toHaveLength(0)
    expect(useChatStore.getState().status).toBe('idle')
  })

  it("stops, and refetches so a reload shows the server's stopped turn", async () => {
    const stream = openStream()
    const api = installAssistantApi({ conversation: conversationOut() })
    onTurn(() => stream.response())
    const { wrapper } = setup()
    const { result } = renderHook(useAll, { wrapper })
    await waitFor(() => expect(result.current.actions.ready).toBe(true))
    await waitFor(() => expect(result.current.conversation.isSuccess).toBe(true))
    const sending = result.current.actions.send('Sick days?')
    stream.push(...started)
    await waitFor(() => expect(useChatStore.getState().status).toBe('streaming'))
    const before = api.requests.current
    act(() => result.current.actions.stop())
    expect(useChatStore.getState().status).toBe('stopped')
    await waitFor(() => expect(api.requests.current).toBeGreaterThan(before))
    await act(() => sending)
  })

  it('asks the same question again from the live turn', async () => {
    installAssistantApi({ conversation: conversationOut() })
    let calls = 0
    const posted = onTurn(() =>
      ++calls === 1
        ? eventStream(started, ['error', { code: 'internal', message: 'Oops.', requestId: null }])
        : eventStream(started, completed),
    )
    const { wrapper } = setup()
    const { result } = renderHook(useAll, { wrapper })
    await waitFor(() => expect(result.current.actions.ready).toBe(true))
    await waitFor(() => expect(result.current.conversation.isSuccess).toBe(true))
    await act(() => result.current.actions.send('Sick days?'))
    expect(useChatStore.getState().status).toBe('error')
    await act(() => result.current.actions.askAgain())
    expect(posted.map((p) => p.question)).toEqual(['Sick days?', 'Sick days?'])
  })

  it('checks who is signed in after a 401 on the send', async () => {
    installAssistantApi({ conversation: conversationOut() })
    let meReads = 0
    server.use(
      http.get(url('/api/v1/me'), () => {
        meReads++
        return HttpResponse.json(meFor('priya'))
      }),
    )
    onTurn(() => problemResponse(401, 'about:blank', 'Not signed in'))
    const { wrapper } = setup()
    const { result } = renderHook(() => ({ actions: useConversationActions(), me: useGetMe() }), {
      wrapper,
    })
    await waitFor(() => expect(result.current.actions.ready).toBe(true))
    await waitFor(() => expect(meReads).toBe(1))
    await act(() => result.current.actions.send('Hello'))
    await waitFor(() => expect(meReads).toBe(2))
  })
})

describe("handing a finished turn to the server's copy", () => {
  const poll = (giveUpAfterMs: number) => ({
    runningPoll: { fastMs: 40, fastForMs: 100_000, slowMs: 40, giveUpAfterMs },
  })
  let giveUpAfterMs = 100_000
  const useFast = () => ({
    actions: useConversationActions(),
    view: useConversationTurns(poll(giveUpAfterMs)),
  })
  const wait = (ms: number) =>
    act(async () => {
      await new Promise((resolve) => setTimeout(resolve, ms))
    })

  async function stopped() {
    const stream = openStream()
    const api = installAssistantApi({ conversation: conversationOut() })
    const posted = onTurn((question) =>
      question === 'again' ? eventStream(started, completed) : stream.response(),
    )
    const { wrapper } = setup()
    const rendered = renderHook(useFast, { wrapper })
    await waitFor(() => expect(rendered.result.current.actions.ready).toBe(true))
    await waitFor(() => expect(rendered.result.current.view.conversation.isSuccess).toBe(true))
    const sending = rendered.result.current.actions.send('Sick days?')
    stream.push(...started)
    await waitFor(() => expect(useChatStore.getState().status).toBe('streaming'))
    return { ...rendered, api, stream, sending, posted }
  }

  it('settles a stopped turn on the second read, after the first still says running', async () => {
    const { result, api, sending } = await stopped()
    api.setCurrent(conversationOut({ turns: [turnOut({ id: TURN_ID, status: 'running' })] }))
    act(() => result.current.actions.stop())
    expect(useChatStore.getState().status).toBe('stopped')
    // The server is still saving it: the live turn stays.
    await waitFor(() => expect(result.current.view.conversation.data?.turns).toHaveLength(1))
    expect(useChatStore.getState().turn).not.toBeNull()
    // It is saved by the next read.
    api.setCurrent(conversationOut({ turns: [turnOut({ id: TURN_ID, status: 'stopped' })] }))
    await waitFor(() => expect(useChatStore.getState().turn).toBeNull())
    expect(result.current.view.live).toBeNull()
    expect(result.current.view.turns.map((turn) => turn.id)).toEqual([TURN_ID])
    await act(() => sending)
  })

  it('gives up after the limit, and keeps the live turn, when the turn never leaves running', async () => {
    giveUpAfterMs = 300
    const { result, api, sending } = await stopped()
    api.setCurrent(conversationOut({ turns: [turnOut({ id: TURN_ID, status: 'running' })] }))
    act(() => result.current.actions.stop())
    await wait(600)
    const reads = api.requests.current
    await wait(250)
    expect(api.requests.current).toBe(reads)
    expect(useChatStore.getState().turn).not.toBeNull()
    await act(() => sending)
  })

  it('keeps asking for a copy that is still running, long after the first few reads', async () => {
    giveUpAfterMs = 100_000
    const { result, api, sending } = await stopped()
    api.setCurrent(conversationOut({ turns: [turnOut({ id: TURN_ID, status: 'running' })] }))
    act(() => result.current.actions.stop())
    await wait(500)
    const early = api.requests.current
    await wait(300)
    // About one read every 40 ms, well past a fixed handful of retries.
    expect(early).toBeGreaterThan(6)
    expect(api.requests.current).toBeGreaterThan(early + 4)
    // And it settles when the copy is finally saved.
    api.setCurrent(conversationOut({ turns: [turnOut({ id: TURN_ID, status: 'stopped' })] }))
    await waitFor(() => expect(useChatStore.getState().turn).toBeNull())
    await act(() => sending)
  })

  it('keeps asking when the server has no copy at all, then gives up', async () => {
    giveUpAfterMs = 300
    const { result, api, sending } = await stopped()
    act(() => result.current.actions.stop())
    await wait(200)
    expect(api.requests.current).toBeGreaterThanOrEqual(4)
    await wait(500)
    const reads = api.requests.current
    await wait(250)
    expect(api.requests.current).toBe(reads)
    await act(() => sending)
  })

  it('lets the next question go out while it waits', async () => {
    const { result, posted, sending } = await stopped()
    act(() => result.current.actions.stop())
    await act(() => result.current.actions.send('again'))
    expect(posted.map((p) => p.question)).toEqual(['Sick days?', 'again'])
    expect(useChatStore.getState().status).toBe('idle')
    await act(() => sending)
  })

  it('keeps waiting for the stopped turn’s copy after a new question replaces it', async () => {
    giveUpAfterMs = 100_000
    const { result, api, sending } = await stopped()
    act(() => result.current.actions.stop())
    await act(() => result.current.actions.send('again'))
    await wait(200)
    const reads = api.requests.current
    await wait(200)
    // Both finished turns are still waiting, so the page still reads.
    expect(api.requests.current).toBeGreaterThan(reads + 2)
    await act(() => sending)
  })
})

describe('giving feedback', () => {
  it('posts the answer for the turn, with the CSRF token, and reads the conversation again', async () => {
    const api = installAssistantApi({ conversation: conversationOut({ turns: [turnOut()] }) })
    const posted = onFeedback((body, turnId) =>
      HttpResponse.json({ turnId, ...body }, { status: 201 }),
    )
    const { wrapper } = setup()
    const { result } = renderHook(
      () => ({ feedback: useFeedback(), conversation: useCurrentConversation() }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.conversation.isSuccess).toBe(true))
    const reads = api.requests.current
    await act(() =>
      result.current.feedback.mutateAsync({ turnId: TURN_ID, data: { helpful: true } }),
    )
    expect(posted).toEqual([{ turnId: TURN_ID, helpful: true }])
    await waitFor(() => expect(api.requests.current).toBeGreaterThan(reads))
  })

  it('sends the reason of a No', async () => {
    installAssistantApi()
    const posted = onFeedback((body, turnId) =>
      HttpResponse.json({ turnId, ...body }, { status: 201 }),
    )
    const { wrapper } = setup()
    const { result } = renderHook(() => useFeedback(), { wrapper })
    await act(() =>
      result.current.mutateAsync({
        turnId: TURN_ID,
        data: { helpful: false, reason: 'Wrong state' },
      }),
    )
    expect(posted).toEqual([{ turnId: TURN_ID, helpful: false, reason: 'Wrong state' }])
  })

  it('reports a refused answer as an error, and does not read the conversation again', async () => {
    const api = installAssistantApi()
    onFeedback(() => problemResponse(409, 'feedback-given', 'Already answered.'))
    const { wrapper } = setup()
    const { result } = renderHook(() => useFeedback(), { wrapper })
    await act(async () => {
      result.current.mutate({ turnId: TURN_ID, data: { helpful: true } })
    })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(api.requests.current).toBe(0)
  })
})

describe('starting a new conversation', () => {
  it('creates one, begins it in the store, and reads the conversation again', async () => {
    const api = installAssistantApi({ conversation: conversationOut({ turns: [turnOut()] }) })
    const { wrapper } = setup()
    const { result } = renderHook(() => useConversationActions(), { wrapper })
    await waitFor(() => expect(result.current.ready).toBe(true))
    useChatStore.setState({ sendError: 'old', draft: 'kept' })
    await act(() => result.current.startNewConversation())
    expect(api.requests.created).toBe(1)
    expect(useChatStore.getState()).toMatchObject({
      conversationId: CONVERSATION_ID,
      turn: null,
      sendError: null,
      draft: 'kept',
    })
  })

  it('says so, and changes nothing, when the conversation cannot be created', async () => {
    installAssistantApi()
    server.use(
      http.post(
        url('/api/v1/assistant/conversations'),
        () => new HttpResponse(null, { status: 500 }),
      ),
    )
    const { wrapper } = setup()
    const { result } = renderHook(() => useConversationActions(), { wrapper })
    await waitFor(() => expect(result.current.ready).toBe(true))
    await act(() => result.current.startNewConversation())
    expect(useChatStore.getState().sendError).toBe('Something went wrong sending that.')
    expect(useChatStore.getState().conversationId).toBeNull()
  })
})

describe('a stopped turn that a newer question came after', () => {
  const FAST = {
    runningPoll: { fastMs: 20, fastForMs: 10_000, slowMs: 20, giveUpAfterMs: 10_000 },
  }
  const useFast = () => ({
    actions: useConversationActions(),
    view: useConversationTurns(FAST),
  })

  async function stoppedThenAsked() {
    const stream = openStream()
    const api = installAssistantApi({ conversation: conversationOut() })
    let calls = 0
    onTurn(() =>
      ++calls === 1
        ? stream.response()
        : eventStream(['turn.started', { turnId: 't-2' }], ['text.delta', { text: 'Next.' }]),
    )
    const { wrapper } = setup()
    const rendered = renderHook(useFast, { wrapper })
    await waitFor(() => expect(rendered.result.current.actions.ready).toBe(true))
    await waitFor(() => expect(rendered.result.current.view.conversation.isSuccess).toBe(true))
    const first = rendered.result.current.actions.send('Sick days?')
    stream.push(...started)
    stream.push('text.delta', { text: 'Half' })
    await waitFor(() => expect(useChatStore.getState().turn?.text).toBe('Half'))
    // The server has it, still running while it saves the stop.
    api.setCurrent(conversationOut({ turns: [turnOut({ id: TURN_ID, status: 'running' })] }))
    act(() => rendered.result.current.actions.stop())
    await act(() => first)
    await act(() => rendered.result.current.actions.send('And carry-over?'))
    return { ...rendered, api }
  }

  it('shows it before the new turn until its own saved copy is there, and hides that copy meanwhile', async () => {
    const { result, api } = await stoppedThenAsked()
    expect(result.current.view.settling.map((s) => s.turn.turnId)).toEqual([TURN_ID])
    // Its saved copy is still `running`: it is not shown twice, and it stays.
    await waitFor(() => expect(result.current.view.conversation.data?.turns).toHaveLength(1))
    expect(result.current.view.turns.map((turn) => turn.id)).toEqual([])
    expect(result.current.view.settling).toHaveLength(1)

    api.setCurrent(
      conversationOut({
        turns: [
          turnOut({ id: TURN_ID, status: 'stopped' }),
          turnOut({ id: 't-2', question: 'And carry-over?' }),
        ],
      }),
    )
    await waitFor(() => expect(result.current.view.settling).toEqual([]))
    await waitFor(() => expect(useChatStore.getState().turn).toBeNull())
    expect(result.current.view.turns.map((turn) => turn.id)).toEqual([TURN_ID, 't-2'])
  })
})

describe('a saved turn that is still running (a reload in the middle of an answer)', () => {
  const FAST = { runningPoll: { fastMs: 30, fastForMs: 10_000, slowMs: 30, giveUpAfterMs: 10_000 } }
  const wait = (ms: number) =>
    act(async () => {
      await new Promise((resolve) => setTimeout(resolve, ms))
    })
  const running = (overrides = {}) =>
    turnOut({
      id: 'r-1',
      status: 'running',
      answerText: 'Partly',
      endedAt: null,
      startedAt: new Date().toISOString(),
      ...overrides,
    })

  it('reads the conversation again until the turn has ended', async () => {
    const api = installAssistantApi({ conversation: conversationOut({ turns: [running()] }) })
    const { wrapper } = setup()
    const { result } = renderHook(() => useCurrentConversation(FAST), { wrapper })
    await waitFor(() => expect(result.current.data?.turns[0]?.status).toBe('running'))
    await waitFor(() => expect(api.requests.current).toBeGreaterThanOrEqual(3))

    api.setCurrent(
      conversationOut({
        turns: [turnOut({ id: 'r-1', status: 'completed', answerText: 'Done.' })],
      }),
    )
    await waitFor(() => expect(result.current.data?.turns[0]?.status).toBe('completed'))
    // Nothing is running now: it stops asking.
    await wait(60)
    const reads = api.requests.current
    await wait(150)
    expect(api.requests.current).toBe(reads)
  })

  it('does not read again for a conversation with nothing running', async () => {
    const api = installAssistantApi({ conversation: conversationOut({ turns: [turnOut()] }) })
    const { wrapper } = setup()
    const { result } = renderHook(() => useCurrentConversation(FAST), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    await wait(150)
    expect(api.requests.current).toBe(1)
  })

  it('keeps asking about a turn whose startedAt is long past: the page counts from first sight, not the server’s clock', async () => {
    const api = installAssistantApi({
      conversation: conversationOut({
        turns: [running({ startedAt: new Date(Date.now() - 30 * 60_000).toISOString() })],
      }),
    })
    const { wrapper } = setup()
    const { result } = renderHook(() => useCurrentConversation(FAST), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    await waitFor(() => expect(api.requests.current).toBeGreaterThanOrEqual(3))
  })

  it('gives up after the limit, counted from the first time the page saw the turn running', async () => {
    const api = installAssistantApi({ conversation: conversationOut({ turns: [running()] }) })
    const { wrapper } = setup()
    const { result } = renderHook(
      () =>
        useCurrentConversation({
          runningPoll: { fastMs: 20, fastForMs: 10_000, slowMs: 20, giveUpAfterMs: 120 },
        }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    await wait(400)
    const reads = api.requests.current
    expect(reads).toBeGreaterThan(1)
    await wait(200)
    expect(api.requests.current).toBe(reads)
  })

  it('leaves the live turn to the settle logic, which reads on its own schedule', async () => {
    const api = installAssistantApi({
      conversation: conversationOut({ turns: [running({ id: TURN_ID })] }),
    })
    useChatStore.setState({
      turn: {
        turnId: TURN_ID,
        question: 'q',
        steps: [],
        text: '',
        citations: [],
        escalation: null,
        error: null,
        completed: false,
        incomplete: false,
        accepted: true,
        toolInputs: {},
      },
      status: 'streaming',
    })
    const { wrapper } = setup()
    const { result } = renderHook(() => useCurrentConversation(FAST), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    await wait(150)
    expect(api.requests.current).toBe(1)
  })
})

describe('the running-turn poll schedule', () => {
  const MIN = 60_000
  const turnsOf = (...turns: Parameters<typeof turnOut>[0][]) =>
    conversationOut({ turns: turns.map((t) => turnOut(t)) })
  const data = turnsOf({ id: 'r-1', status: 'running' })

  it('asks every 2 s for the first 2 minutes, then every 15 s, and stops 11 minutes after first sight', () => {
    const poll = createRunningPoller()
    const t0 = 1_000_000
    expect(poll(data, null, t0)).toBe(2000)
    expect(poll(data, null, t0 + 119_000)).toBe(2000)
    expect(poll(data, null, t0 + 2 * MIN)).toBe(15_000)
    expect(poll(data, null, t0 + 10 * MIN)).toBe(15_000)
    expect(poll(data, null, t0 + 11 * MIN - 1)).toBe(15_000)
    expect(poll(data, null, t0 + 11 * MIN)).toBe(false)
  })

  it('counts from first sight on the page’s clock, whatever startedAt says', () => {
    const poll = createRunningPoller()
    const odd = turnsOf({ id: 'r-1', status: 'running', startedAt: '2001-01-01T00:00:00Z' })
    expect(poll(odd, null, 5_000)).toBe(2000)
    expect(poll(odd, null, 5_000 + 3 * MIN)).toBe(15_000)
  })

  it('stops when nothing is running, forgets the turn, and starts a new run afresh', () => {
    const poll = createRunningPoller()
    expect(poll(data, null, 0)).toBe(2000)
    expect(poll(data, null, 3 * MIN)).toBe(15_000)
    expect(poll(turnsOf({ id: 'r-1', status: 'completed' }), null, 3 * MIN + 1)).toBe(false)
    expect(poll(data, null, 4 * MIN)).toBe(2000)
  })

  it('leaves the page’s own live turn alone, and polls the other running turns', () => {
    const poll = createRunningPoller()
    const both = turnsOf({ id: 'r-1', status: 'running' }, { id: 'r-2', status: 'running' })
    expect(poll(both, 'r-1', 0)).toBe(2000)
    expect(poll(turnsOf({ id: 'r-1', status: 'running' }), 'r-1', 0)).toBe(false)
  })

  it('also asks about a finished turn the page holds until its copy is saved, missing or running', () => {
    const poll = createRunningPoller()
    const none = turnsOf()
    expect(poll(none, null, 0, ['w-1'])).toBe(2000)
    expect(poll(none, null, 3 * MIN, ['w-1'])).toBe(15_000)
    const running = turnsOf({ id: 'w-1', status: 'running' })
    expect(poll(running, null, 3 * MIN + 1, ['w-1'])).toBe(15_000)
    // Saved: nothing more to ask.
    expect(poll(turnsOf({ id: 'w-1', status: 'stopped' }), null, 3 * MIN + 2, ['w-1'])).toBe(false)
    // And it gives up 11 minutes after first sight, like any other.
    const late = createRunningPoller()
    expect(late(none, null, 0, ['w-1'])).toBe(2000)
    expect(late(none, null, 11 * MIN, ['w-1'])).toBe(false)
  })

  it('leaves the turn being received alone even when a held finished turn is waiting', () => {
    const poll = createRunningPoller()
    const both = turnsOf({ id: 'r-1', status: 'running' }, { id: 'w-1', status: 'running' })
    expect(poll(both, 'r-1', 0, ['w-1'])).toBe(2000)
    expect(poll(turnsOf({ id: 'r-1', status: 'running' }), 'r-1', 1, [])).toBe(false)
  })

  it('has nothing to ask about before there is a conversation', () => {
    expect(createRunningPoller()(null, null, 0)).toBe(false)
    expect(createRunningPoller()(undefined, null, 0)).toBe(false)
  })
})
