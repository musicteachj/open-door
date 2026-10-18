import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getCurrentConversation,
  getGetAssistantBudgetQueryKey,
  getGetCurrentConversationQueryKey,
  getGetMeQueryKey,
  useCreateConversation,
  useGetAssistantBudget,
  useGetAssistantTexts,
  useGetCurrentConversation,
  useGiveFeedback,
  type ConversationOut,
} from '@/api/generated'
import { registerReset } from '@/lib/identity'
import { conversationCopy } from '@/components/assistant/labels'
import { numberBySection } from '@/components/assistant/sources'
import { useChatStore, type ChatState, type SendDeps } from './store'

// The hooks the conversation page uses: the stored conversation (TanStack Query), the API's fixed
// texts, and the actions that join the chat store to the server.

/**
 * The stored conversation with each turn's citations numbered by section, so the components take
 * them as they are. A module-level function, so TanStack Query reuses its result until the data
 * changes.
 */
function numberConversation(data: ConversationOut | null): ConversationOut | null {
  if (data === null) return null
  return {
    ...data,
    turns: data.turns.map((turn) => ({ ...turn, citations: numberBySection(turn.citations) })),
  }
}

/**
 * How the conversation is read again while a turn has not reached its saved form: a saved turn
 * still `running` (a reload in the middle of one), and a finished turn the page holds that is not
 * saved yet or whose copy is still `running` (the server saves a stopped turn in a cleanup that can
 * finish after the read). The server treats a running turn as abandoned only after 10 minutes, so
 * the page keeps asking: every 2 s for the first 2 minutes, then every 15 s, and it stops about 11
 * minutes after it first saw the turn waiting. Counted on the page's own clock from first sight,
 * never from the server's `startedAt`, which is another machine's clock.
 */
export const RUNNING_POLL = {
  fastMs: 2000,
  fastForMs: 2 * 60_000,
  slowMs: 15_000,
  giveUpAfterMs: 11 * 60_000,
}
export type RunningPoll = typeof RUNNING_POLL

/**
 * The refetch interval for the current conversation, as a function of what it holds. It remembers
 * when each waiting turn was first seen. `streaming` is the turn the page is receiving now: its
 * saved copy is expected to be `running`, so it is left alone. `waiting` is the finished turns the
 * page holds until their copy is saved; they count until it is.
 */
export function createRunningPoller(poll: RunningPoll = RUNNING_POLL) {
  const firstSeen = new Map<string, number>()
  return (
    data: ConversationOut | null | undefined,
    streaming: string | readonly (string | null | undefined)[] | null | undefined,
    now: number = Date.now(),
    waiting: readonly string[] = [],
  ): number | false => {
    const receiving = new Set([streaming].flat())
    const saved = new Map((data?.turns ?? []).map((turn) => [turn.id, turn]))
    const pending = new Set<string>()
    for (const turn of saved.values()) {
      if (turn.status === 'running' && !receiving.has(turn.id)) pending.add(turn.id)
    }
    for (const id of waiting) {
      const copy = saved.get(id)
      if (copy === undefined || copy.status === 'running') pending.add(id)
    }
    // A turn that is no longer pending is forgotten, so one that waits again starts afresh.
    for (const id of [...firstSeen.keys()]) {
      if (!pending.has(id)) firstSeen.delete(id)
    }
    let interval: number | false = false
    for (const id of pending) {
      if (!firstSeen.has(id)) firstSeen.set(id, now)
      const since = now - firstSeen.get(id)!
      if (since >= poll.giveUpAfterMs) continue
      const next = since < poll.fastForMs ? poll.fastMs : poll.slowMs
      interval = interval === false ? next : Math.min(interval, next)
    }
    return interval
  }
}

type SettleOptions = { runningPoll?: RunningPoll }

/** The IDs of the finished live turns still waiting for their saved copy. */
function waitingTurnIds(state: ChatState): string[] {
  const ids = state.settling.map((entry) => entry.turn.turnId)
  const { turn, status } = state
  if (turn !== null && status !== 'sending' && status !== 'streaming') ids.push(turn.turnId)
  return ids.filter((id): id is string => id !== null)
}

/** The turn the page is receiving now, if any. */
function streamingTurnId(state: ChatState): string | null {
  return state.turn !== null && (state.status === 'sending' || state.status === 'streaming')
    ? state.turn.turnId
    : null
}

/**
 * The person's newest conversation (null before their first question). It also hands a finished
 * live turn (completed, stopped, errored, or ended by its escalation) to the server's copy: the
 * store keeps showing the turn until the refetched conversation holds its id with a status other
 * than `running`, so nothing flickers or disappears. While the copy is missing or still running the
 * poll below reads again, then gives up (after about 11 minutes) and leaves the turn showing. Call it once per page
 * (`useConversationTurns` does, and returns the query).
 */
export function useCurrentConversation({ runningPoll = RUNNING_POLL }: SettleOptions = {}) {
  const [pollRunning] = useState(() => createRunningPoller(runningPoll))
  const query = useGetCurrentConversation({
    query: {
      select: numberConversation,
      // Turns that are not in their saved form yet are read again until they are (`RUNNING_POLL`):
      // one this page did not start (a reload, or another tab) is never announced to it, and the
      // page's own finished turns wait for their copy.
      refetchInterval: (current) => {
        const state = useChatStore.getState()
        return pollRunning(
          current.state.data,
          streamingTurnId(state),
          Date.now(),
          waitingTurnIds(state),
        )
      },
    },
  })
  // The finished turns waiting for their saved copy: the live one if it is done, and any that a
  // newer question came after. Each goes as soon as its own copy is there (not `running`).
  const waitingKey = useChatStore((s) => waitingTurnIds(s).join(','))
  const waiting = useMemo(() => (waitingKey === '' ? [] : waitingKey.split(',')), [waitingKey])
  const settle = useChatStore((s) => s.settle)
  const storedKey = waiting
    .filter((id) => query.data?.turns.some((turn) => turn.id === id && turn.status !== 'running'))
    .join(',')
  useEffect(() => {
    for (const id of storedKey === '' ? [] : storedKey.split(',')) settle(id)
  }, [storedKey, settle])
  return query
}

/**
 * The API's own words for what the browser refuses without a request. Fetched once (they are
 * fixed), so the page waits for them before the composer runs.
 */
export function useAssistantTexts() {
  return useGetAssistantTexts({ query: { staleTime: Infinity } })
}

/**
 * The budget route, for a person with no conversation yet (the conversation carries its own). It
 * is read only while there is none, and again whenever the conversation is (a refused send, a new
 * conversation), so the home shows the banner before the first question.
 */
export function useBudgetBeforeConversation(hasConversation: boolean | undefined) {
  return useGetAssistantBudget({
    query: { enabled: hasConversation === false, staleTime: BUDGET_STALE_MS },
  })
}

/** A budget read is good this long: it is asked again when a send is refused. */
const BUDGET_STALE_MS = 5000

/**
 * The stored turns to show, the finished turns still waiting for their saved copy (`settling`),
 * and the live one. While a turn is held by the page its stored copy (once the server has one) is
 * left out of `turns`, so the same turn is never drawn twice.
 */
export function useConversationTurns(options: SettleOptions = {}) {
  const conversation = useCurrentConversation(options)
  const { data } = conversation
  const live = useChatStore((s) => s.turn)
  const settling = useChatStore((s) => s.settling)
  // The page's own turns are drawn from the store, so their saved copies are left out here.
  const heldKey = [live?.turnId, ...settling.map((entry) => entry.turn.turnId)]
    .filter((id) => id != null)
    .join(',')
  const turns = useMemo(() => {
    const held = new Set(heldKey.split(','))
    return (data?.turns ?? []).filter((turn) => !held.has(turn.id))
  }, [data, heldKey])
  return { conversation, turns, live, settling }
}

/**
 * Reads the conversation again, and the budget with it: the banner for a person with no
 * conversation yet comes from the budget route, and both change together.
 */
function invalidateConversation(queryClient: QueryClient) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: getGetCurrentConversationQueryKey() }),
    queryClient.invalidateQueries({ queryKey: getGetAssistantBudgetQueryKey() }),
  ])
}

// The conversation being created for a first question, shared by every component that sends (the
// home and the conversation are different components, and one replaces the other while this is
// still in flight). Forgotten when the person changes or a new conversation is started on purpose.
let creating: { promise: Promise<string> } | null = null
registerReset(() => {
  creating = null
})

/**
 * Sending, stopping, and starting over. `send` does nothing until the API's texts have loaded (the
 * page waits for them, so this only guards a send that races the page). Retry and Ask again send
 * the live turn's own question again.
 */
export function useConversationActions() {
  const queryClient = useQueryClient()
  const { data: texts } = useAssistantTexts()
  const create = useCreateConversation()
  const { mutateAsync: createConversation } = create

  const deps = useCallback(async (): Promise<SendDeps | null> => {
    if (texts === undefined) return null
    // The conversation the page showed, or the one the last send created and the read has not
    // caught up with yet. Without the read there is no way to know whether one exists.
    const known = useChatStore.getState().conversationId
    const cached = queryClient.getQueryData<ConversationOut | null>(
      getGetCurrentConversationQueryKey(),
    )
    const current =
      known !== null || cached !== undefined
        ? (cached ?? null)
        : await queryClient.ensureQueryData({
            queryKey: getGetCurrentConversationQueryKey(),
            queryFn: ({ signal }) => getCurrentConversation({ signal }),
          })
    return {
      conversationId: known ?? current?.id ?? null,
      // One creation at a time: a Stop and a new question while the first is still being created
      // wait for it, instead of making a second, empty conversation.
      createConversation: () => {
        if (creating !== null) return creating.promise
        const entry: { promise: Promise<string> } = { promise: Promise.resolve('') }
        entry.promise = (async () => {
          try {
            const created = await createConversation()
            void invalidateConversation(queryClient)
            return created.id
          } finally {
            if (creating === entry) creating = null
          }
        })()
        creating = entry
        return entry.promise
      },
      invalidateConversation: () => void invalidateConversation(queryClient),
      // Not an invented value: the cached data goes, and the active read starts over.
      forgetConversation: () =>
        void queryClient.resetQueries({ queryKey: getGetCurrentConversationQueryKey() }),
      onUnauthorized: () => void queryClient.invalidateQueries({ queryKey: getGetMeQueryKey() }),
      texts,
    }
  }, [queryClient, texts, createConversation])

  const send = useCallback(
    async (question: string) => {
      let ready: SendDeps | null
      try {
        ready = await deps()
      } catch {
        // The read that says whether there is a conversation failed. The composer calls `void
        // send(...)`, so nobody would catch it: say the send failed, and keep the draft.
        useChatStore.setState({ sendError: conversationCopy.sendFailed })
        return
      }
      if (ready !== null) await useChatStore.getState().send(question, ready)
    },
    [deps],
  )

  const stop = useCallback(() => {
    useChatStore
      .getState()
      .stop({ invalidateConversation: () => void invalidateConversation(queryClient) })
  }, [queryClient])

  /** Retry (after an error) and Ask again (after Stop): the live turn's question, sent again. */
  const askAgain = useCallback(async () => {
    const question = useChatStore.getState().turn?.question
    if (question !== undefined) await send(question)
  }, [send])

  /** "Start a new conversation": a new one on the server, and the old one's live turn dropped. */
  const startNewConversation = useCallback(async () => {
    try {
      creating = null
      const created = await createConversation()
      useChatStore.getState().beginConversation(created.id)
      await invalidateConversation(queryClient)
    } catch {
      useChatStore.setState({ sendError: conversationCopy.sendFailed })
    }
  }, [createConversation, queryClient])

  return { send, stop, askAgain, startNewConversation, ready: texts !== undefined }
}

/** Thumbs up or down on an answer. The conversation is read again so the answer shows its feedback. */
export function useFeedback() {
  const queryClient = useQueryClient()
  return useGiveFeedback({
    mutation: { onSuccess: () => invalidateConversation(queryClient) },
  })
}
