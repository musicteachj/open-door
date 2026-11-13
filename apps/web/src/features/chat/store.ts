import { create } from 'zustand'
import type { AssistantTextsOut, CitationOut, ProposalOut } from '@/api/generated'
import { conversationCopy, toolCallLine, toolRunningLine } from '@/components/assistant/labels'
import { numberBySection } from '@/components/assistant/sources'
import type { StatusStep } from '@/components/assistant/status-line'
import { trimLikePython } from '@/components/assistant/text-count'
import { ApiError } from '@/lib/api-fetch'
import { registerReset } from '@/lib/identity'
import { kindOfPersonalData } from '@/lib/personal-data'
import { streamTurn, type EscalationEvent, type TurnStreamEvent } from '@/lib/stream-turn'

// The chat session: the draft, and the one turn that is live (the one being answered now, or the
// one that just finished and whose stored copy the page has not fetched yet). Everything stored
// on the server comes from TanStack Query (`use-conversation.ts`); this holds only what the
// browser knows before the server does.

/**
 * `idle`: nothing is being answered (a finished turn can still be shown, see `turn.completed`).
 * `sending`: the question is on its way. `streaming`: the answer is arriving. `error` and
 * `stopped`: the turn ended that way, and its partial answer is still shown.
 */
export type ChatStatus = 'idle' | 'sending' | 'streaming' | 'error' | 'stopped'

/** An escalation that arrived on the stream. Only a live one is announced to a screen reader. */
export type LiveEscalation = EscalationEvent & { live: true }

export type LiveTurn = {
  /** Null until `turn.started`. */
  turnId: string | null
  /** The question as it was sent (trimmed). */
  question: string
  steps: StatusStep[]
  text: string
  /** Numbered by section as they arrive (`numberBySection`), so the components never number. */
  citations: CitationOut[]
  escalation: LiveEscalation | null
  /**
   * The confirm cards the turn prepared, in the order they arrived, one per id (a newer event for
   * the same id replaces it). Kept through `text.retracted`: a card is not answer text. The
   * stored copy takes over when the conversation is read again.
   */
  proposals: ProposalOut[]
  /** The stream's `error` event. */
  error: { code: string; message: string } | null
  /** `turn.completed` arrived. The turn stays until the refetched conversation holds it. */
  completed: boolean
  /**
   * The server has answered the send with a stream (status 200). From then on it has the turn and
   * will save it, even if no event has been read yet, so a Stop is not a send that went nowhere.
   */
  accepted: boolean
  /** The output limit cut the answer off. */
  incomplete: boolean
  /** What each running tool was asked, by tool-call id, to word its line when it finishes. */
  toolInputs: Record<string, { name: string; summary: string }>
}

export type SendDeps = {
  /** The conversation to ask in, or null when there is none yet: the first question creates it. */
  conversationId: string | null
  /** Creates a conversation and returns its id. */
  createConversation: () => Promise<string>
  /** Asks the server for the conversation again. Never writes the query's data (see the backlog). */
  invalidateConversation: () => void
  /**
   * The conversation this was sent to is gone: drops the cached copy (it still holds the dead id)
   * and reads again, so the next send cannot go to the dead id before the read lands.
   */
  forgetConversation: () => void
  /** The server said 401 to the send: the session guard should check who is signed in. */
  onUnauthorized: () => void
  /** The API's own words for the two refusals the browser makes without a request. */
  texts: AssistantTextsOut
}

/**
 * How a send ended, for a caller that must know whether the server took the question.
 * `not-sent`: it was refused here, or the API refused it before taking it (still answering,
 * waiting, nothing to send to, or a 4xx problem from the API: 409 turn-running, 422 personal data).
 * `accepted`: the server took it and this is its turn, resolved once the stream is over.
 * `failed-after-accept`: the server may hold the question but its turn is not known, so a caller
 * must not send it again.
 * One rule: "never sent twice" wins over "always retryable". `not-sent` only when the request
 * certainly never reached the server: it was refused locally before it was issued, or the API
 * itself answered with a 4xx problem (409 turn running, 422 personal data, 404, 429, 401, 403).
 * Anything after the request was issued that is not such an answer is `failed-after-accept`: a 5xx,
 * a response that is not the API's problem (a proxy's 502 or 504, a 200 HTML page), a stream that
 * ended before it named its turn, a network failure (a reset connection cannot be told from being
 * offline), or an abort (the visitor's Stop, leaving). The server starts the turn's row before it
 * streams and saves a turn whose client left as stopped, so a Stop before any response can still
 * leave a (stopped) turn there. The chat's own Stop puts
 * the question back in the box because nothing is shown for it, which is about the draft, not
 * about whether the server holds it; so a caller must not give the question back.
 */
export type SendOutcome =
  { kind: 'not-sent' } | { kind: 'accepted'; turnId: string } | { kind: 'failed-after-accept' }

export const NOT_SENT: SendOutcome = { kind: 'not-sent' }

/** A finished live turn whose saved copy has not arrived yet, shown in order until it does. */
export type SettlingTurn = { turn: LiveTurn; phase: 'idle' | 'error' | 'stopped' }

/**
 * Where a send came from. `composer`: the person typed the question, so the box is emptied once
 * the server takes it. `again`: Retry, Ask again, or Try again re-sent a turn's question, and what
 * is in the box (something typed since, even if it matches) is not theirs to clear.
 */
export type SendOrigin = 'composer' | 'again'

export type ChatState = {
  draft: string
  status: ChatStatus
  turn: LiveTurn | null
  /**
   * Finished turns (stopped, errored, completed) that a newer question came after, before the
   * server's copy of them arrived. They stay on the page, in order before `turn`, and go one by
   * one as their copy does.
   */
  settling: readonly SettlingTurn[]
  /**
   * Turns whose escalation panel is about to appear for the first time from the saved copy, because
   * the live copy had none (a stop closed the stream before the escalation came). The saved panel
   * announces itself once for these, then `consumeAnnouncement` forgets the turn, so a later
   * render, a refetch, or a reload stays silent.
   */
  panelsToAnnounce: readonly string[]
  /** The conversation the last send went to, so a quick second question does not create another. */
  conversationId: string | null
  /** Why the last send did not go, shown under the box. The draft is kept. */
  sendError: string | null
  /**
   * A send is waiting for "Start a new conversation" to finish creating the conversation it will
   * go to. The composer shows its busy state meanwhile, so a second Enter is not a silent no-op.
   */
  waitingToSend: boolean
  /** The personal-data text, set while the draft holds a number the check refuses. */
  warning: string | null
  /** The send was refused because the conversation can't continue: offer a new one. */
  offerNewConversation: boolean
  /**
   * The offer comes from a refusal whose own words, under the box, say why (the conversation is
   * too long for what is left of the budget): the notice shows only its button, not the
   * long-conversation words, which would give another reason.
   */
  offerWithoutNoticeWords: boolean
  setDraft: (draft: string) => void
  /**
   * Asks a question. Does nothing for a blank one. While an answer is coming it sends nothing and
   * shows the "still answering" text. A question that looks like a Social Security or card number
   * is not sent and sets `warning`. Resolves to how the send ended (`SendOutcome`) when it is over.
   * `onAccepted` is called once, as soon as the server's turn ID is known, so a caller need not
   * wait for the whole answer to learn it. `onIssued` is called once, right before the request
   * goes out: from then on the server may hold the question.
   */
  send: (
    question: string,
    deps: SendDeps,
    origin?: SendOrigin,
    onAccepted?: (turnId: string) => void,
    onIssued?: () => void,
  ) => Promise<SendOutcome>
  /** Stops the answer: the connection closes, and the turn shows "Stopped" with what arrived. */
  stop: (deps: Pick<SendDeps, 'invalidateConversation'>) => void
  /** The refetched conversation holds the finished turn: drop the live copy. */
  settle: (turnId: string) => void
  /** The saved panel for this turn has announced itself (or has none to announce): forget it. */
  consumeAnnouncement: (turnId: string) => void
  /** A new conversation was created: forget the old one's live turn and errors. */
  beginConversation: (conversationId: string) => void
}

/** A question is being sent or is streaming its answer. */
export function isRunning(state: Pick<ChatState, 'status'>): boolean {
  return state.status === 'sending' || state.status === 'streaming'
}

/** A question is being sent or answered, or one is waiting for its conversation to be created. */
export function isChatBusy(state: Pick<ChatState, 'status' | 'waitingToSend'>): boolean {
  return isRunning(state) || state.waitingToSend
}

const EMPTY = {
  draft: '',
  status: 'idle',
  turn: null,
  settling: [],
  panelsToAnnounce: [],
  conversationId: null,
  sendError: null,
  waitingToSend: false,
  warning: null,
  offerNewConversation: false,
  offerWithoutNoticeWords: false,
} as const

/** Error codes that mean no more questions can be asked: the conversation's banner says why. */
const BUDGET_CODES: ReadonlySet<string> = new Set(['budget-sandbox', 'budget-daily', 'spend-limit'])

// Each send belongs to one generation. A reset starts a new one and aborts the stream in flight, so
// a late event (even from a stream that ignores the signal) never reaches the next person.
let generation = 0
let inFlight: AbortController | null = null
// Stop was pressed after the server answered but before it announced the turn: the turn is
// stopped as soon as its id is known.
let pendingStop = false
// Counts only the changes of who is asking (an identity reset, a new conversation). A stopped send
// is still its own person's, so a conversation it was creating is kept when it arrives.
let epoch = 0

function freshTurn(question: string): LiveTurn {
  return {
    turnId: null,
    question,
    steps: [],
    text: '',
    citations: [],
    escalation: null,
    proposals: [],
    error: null,
    completed: false,
    incomplete: false,
    accepted: false,
    toolInputs: {},
  }
}

const allDone = (steps: StatusStep[]) => steps.map((step) => ({ ...step, done: true }))

/** Adds a step. A `status` step before it is finished by the next step, a tool step by its end. */
function withStep(turn: LiveTurn, step: StatusStep): LiveTurn {
  const steps = turn.steps.map((earlier) =>
    earlier.id.startsWith('status-') ? { ...earlier, done: true } : earlier,
  )
  return { ...turn, steps: [...steps, step] }
}

/** The turn after one stream event. The second part is true when the conversation should refetch. */
function applyEvent(turn: LiveTurn, event: TurnStreamEvent): [LiveTurn, boolean] {
  switch (event.type) {
    case 'turn.started':
      return [{ ...turn, turnId: event.data.turnId }, false]
    case 'status':
      return [
        withStep(turn, { id: `status-${turn.steps.length}`, text: event.data.text, done: false }),
        false,
      ]
    case 'tool.started': {
      const { id, name, summary } = event.data
      const again = Object.values(turn.toolInputs).some((earlier) => earlier.name === name)
      const text = toolRunningLine(name, again)
      const step: StatusStep = { id: `tool-${id}`, text, done: false }
      const toolInputs = { ...turn.toolInputs, [id]: { name, summary } }
      // The scripted model (and a real one's note) says "Searching the handbook…" just before the
      // search itself: the tool takes that line over rather than adding a second.
      const last = turn.steps.at(-1)
      if (last !== undefined && last.id.startsWith('status-') && !last.done && last.text === text) {
        return [{ ...turn, steps: [...turn.steps.slice(0, -1), step], toolInputs }, false]
      }
      return [{ ...withStep(turn, step), toolInputs }, false]
    }
    case 'tool.finished': {
      const { id, ok } = event.data
      const input = turn.toolInputs[id]
      const steps = turn.steps.map((step) =>
        step.id === `tool-${id}`
          ? {
              ...step,
              done: true,
              text: input
                ? toolCallLine({ name: input.name, inputSummary: input.summary, ok })
                : step.text,
            }
          : step,
      )
      return [{ ...turn, steps }, false]
    }
    case 'text.delta':
      return [
        {
          ...turn,
          text: turn.text + event.data.text,
          steps: turn.steps.map((step) =>
            step.id.startsWith('status-') ? { ...step, done: true } : step,
          ),
        },
        false,
      ]
    case 'text.retracted':
      // The note that was shown follows as a `status` event, so nothing is added here.
      return [{ ...turn, text: '', citations: [] }, false]
    case 'citation':
      return [{ ...turn, citations: numberBySection([...turn.citations, event.data]) }, false]
    case 'escalation':
      return [{ ...turn, escalation: { ...event.data, live: true } }, false]
    case 'proposal': {
      const at = turn.proposals.findIndex((earlier) => earlier.id === event.data.id)
      // A card with a new id replaces the turn's earlier pending cards on the server, which
      // cancels them as `replaced` but sends only the new one, so the live copies say so too.
      // It replaces pending cards across the whole conversation, so a new card also reads the
      // conversation again: the stored turns' cards then say so as well.
      const proposals =
        at === -1
          ? [
              ...turn.proposals.map((earlier): ProposalOut =>
                earlier.status === 'pending'
                  ? {
                      ...earlier,
                      status: 'canceled',
                      canceledReason: 'replaced',
                      turnRunning: false,
                    }
                  : earlier,
              ),
              event.data,
            ]
          : turn.proposals.map((earlier, index) => (index === at ? event.data : earlier))
      return [{ ...turn, proposals }, at === -1]
    }
    case 'error':
      return [
        {
          ...turn,
          steps: allDone(turn.steps),
          error: { code: event.data.code, message: event.data.message },
        },
        // The failed turn is stored (and a budget stop changes the banner), so read it again.
        true,
      ]
    case 'turn.completed':
      return [
        {
          ...turn,
          turnId: event.data.turnId,
          steps: allDone(turn.steps),
          completed: true,
          incomplete: event.data.incomplete === true,
        },
        true,
      ]
  }
}

/**
 * The API itself refused the question before taking it: a 4xx with its own problem document (401,
 * 403, 404, 409, 422, 429). A 5xx, or a response that is not the API's problem (a proxy's 502 or
 * 504, a 200 HTML page), says nothing about whether the turn started.
 */
function refusedByApi(error: unknown): boolean {
  return (
    error instanceof ApiError && error.problem !== null && error.status >= 400 && error.status < 500
  )
}

function problemText(error: ApiError): string {
  return error.problem?.detail || conversationCopy.sendFailed
}

export const useChatStore = create<ChatState>((set, get) => ({
  ...EMPTY,

  setDraft: (draft) =>
    set((state) => {
      if (draft === state.draft) return {}
      return {
        draft,
        // The old message is about the old text. The warning stays only while the number does.
        sendError: null,
        warning:
          state.warning !== null && kindOfPersonalData(draft) === null ? null : state.warning,
      }
    }),

  async send(question, deps, origin = 'composer', onAccepted, onIssued) {
    const trimmed = trimLikePython(question)
    if (trimmed === '') return NOT_SENT
    if (isRunning(get())) {
      set({ sendError: deps.texts.stillAnswering })
      return NOT_SENT
    }
    if (kindOfPersonalData(trimmed) !== null) {
      set({ warning: deps.texts.personalData })
      return NOT_SENT
    }

    const mine = ++generation
    const myEpoch = epoch
    const controller = new AbortController()
    inFlight?.abort()
    inFlight = controller
    pendingStop = false
    set((state) => ({
      status: 'sending',
      turn: freshTurn(trimmed),
      // A finished turn whose saved copy has not come yet stays on the page, before the new one,
      // so a new question (or one that is then refused) never makes an answer vanish.
      settling:
        state.turn !== null && state.turn.turnId !== null
          ? [...state.settling, { turn: state.turn, phase: finishedPhase(state.status) }]
          : state.settling,
      sendError: null,
      warning: null,
      offerNewConversation: false,
      offerWithoutNoticeWords: false,
    }))

    const live = () => mine === generation && !controller.signal.aborted
    // What the server did with this send, whoever is still watching: it answered with a stream,
    // and the turn's ID once an event gives it.
    let responded = false
    // The request was issued: from here the server may hold the question even if no response was
    // read, so an abort (stop, leaving) leaves it unknown and a caller must not send it again.
    let requested = false
    let acceptedId: string | null = null
    const outcome = (): SendOutcome => {
      if (acceptedId !== null) return { kind: 'accepted', turnId: acceptedId }
      return responded || (requested && controller.signal.aborted)
        ? { kind: 'failed-after-accept' }
        : NOT_SENT
    }
    const onEvent = (event: TurnStreamEvent) => {
      if (event.type === 'turn.started' || event.type === 'turn.completed') {
        if (acceptedId === null && live()) {
          acceptedId = event.data.turnId
          onAccepted?.(event.data.turnId)
        }
      }
      if (!live()) return
      let refetch = false
      set((state) => {
        if (state.turn === null) return {}
        const [turn, refresh] = applyEvent(state.turn, event)
        refetch = refresh
        return {
          turn,
          // The first event means the server took the question, so it is no longer a draft. Text
          // typed since then stays.
          draft:
            event.type === 'turn.started' &&
            origin === 'composer' &&
            trimLikePython(state.draft) === trimmed
              ? ''
              : state.draft,
          // "Still answering" is about this answer, which has now ended.
          sendError:
            event.type === 'error' || event.type === 'turn.completed' ? null : state.sendError,
          // Only this conversation's size is the problem (a new one would fit in what is left),
          // as for the 429 of the same type: offer a new conversation, with the error's own words
          // standing for the notice's. It is not a BUDGET_CODES stop.
          ...(event.type === 'error' && event.data.code === 'budget-conversation'
            ? { offerNewConversation: true, offerWithoutNoticeWords: true }
            : {}),
          status:
            event.type === 'error'
              ? 'error'
              : event.type === 'turn.completed'
                ? 'idle'
                : state.status === 'sending'
                  ? 'streaming'
                  : state.status,
        }
      })
      if (refetch) deps.invalidateConversation()
      if (pendingStop && event.type === 'turn.started') {
        pendingStop = false
        get().stop(deps)
      }
    }

    try {
      let conversationId = deps.conversationId
      if (conversationId === null) conversationId = await deps.createConversation()
      if (!live()) {
        // A send stopped while it was creating the conversation still keeps it, so the next
        // question uses it, unless the person changed or one is already remembered.
        if (deps.conversationId === null && myEpoch === epoch && get().conversationId === null) {
          set({ conversationId })
        }
        return NOT_SENT
      }
      set({ conversationId })
      requested = true
      onIssued?.()
      await streamTurn(conversationId, trimmed, {
        signal: controller.signal,
        onEvent,
        onResponse: () => {
          responded = true
          if (!live()) return
          set((state) => (state.turn === null ? {} : { turn: { ...state.turn, accepted: true } }))
        },
      })
      if (!live()) return outcome()
      // The stream ended. With no closing event the connection dropped, which the server saves as
      // stopped.
      endWithoutClosingEvent(deps, origin)
    } catch (error) {
      if (!live()) return outcome()
      const turn = get().turn
      if (
        turn !== null &&
        !(error instanceof ApiError) &&
        (turn.turnId !== null || turn.accepted)
      ) {
        // The server had answered: keep what arrived (it saved the turn as stopped), or, if it had
        // not yet said which turn, treat it as a turn it holds all the same.
        endWithoutClosingEvent(deps, origin)
        return outcome()
      }
      failSend(error, deps)
      // A failure before the request was issued is not sent, and so is a refusal the API itself
      // gave (`refusedByApi`). Anything else after it was issued is unknown: it may have arrived.
      if (requested && !refusedByApi(error)) return { kind: 'failed-after-accept' }
      return NOT_SENT
    } finally {
      if (inFlight === controller) inFlight = null
    }
    return outcome()
  },

  stop(deps) {
    const { status, turn } = get()
    if (turn === null || !isRunning({ status })) return
    if (turn.turnId === null && turn.accepted) {
      // The server has answered, so it has the turn and will save it stopped; only its id has not
      // been read yet. Nothing is shown or put back in the box until it is (`pendingStop`).
      pendingStop = true
      return
    }
    inFlight?.abort()
    inFlight = null
    if (turn.turnId === null) {
      // The server has not answered, so no turn can exist yet and there is nothing to show as
      // stopped. The question goes back in the box (unless something else is there now).
      set((state) => ({
        status: 'idle',
        turn: null,
        sendError: null,
        draft: state.draft === '' ? turn.question : state.draft,
      }))
    } else {
      set({ status: 'stopped', turn: { ...turn, steps: allDone(turn.steps) }, sendError: null })
    }
    deps.invalidateConversation()
  },

  settle(turnId) {
    const { turn, status, settling, panelsToAnnounce } = get()
    // A panel that never came down the stream is new to the person when the saved copy brings it.
    // Only a turn that didn't complete can gain one: a completed turn's escalation came before its
    // `turn.completed`.
    const withAnnouncement = (live: LiveTurn) =>
      live.escalation === null && live.turnId !== null && !live.completed
        ? [...panelsToAnnounce, live.turnId]
        : panelsToAnnounce
    // A turn waiting behind a newer one goes as soon as its saved copy is there.
    const waiting = settling.find((entry) => entry.turn.turnId === turnId)
    if (waiting !== undefined) {
      set({
        settling: settling.filter((entry) => entry !== waiting),
        panelsToAnnounce: withAnnouncement(waiting.turn),
      })
      return
    }
    // Any turn that has finished (completed, stopped, errored, or ended by its escalation) goes
    // to the server's copy. One still coming does not.
    if (turn === null || turn.turnId !== turnId) return
    if (isRunning({ status })) return
    set({ status: 'idle', turn: null, panelsToAnnounce: withAnnouncement(turn) })
  },

  consumeAnnouncement(turnId) {
    const { panelsToAnnounce } = get()
    if (!panelsToAnnounce.includes(turnId)) return
    set({ panelsToAnnounce: panelsToAnnounce.filter((id) => id !== turnId) })
  },

  beginConversation(conversationId) {
    generation++
    epoch++
    inFlight?.abort()
    inFlight = null
    set({
      conversationId,
      status: 'idle',
      turn: null,
      settling: [],
      panelsToAnnounce: [],
      sendError: null,
      warning: null,
      offerNewConversation: false,
      offerWithoutNoticeWords: false,
    })
  },
}))

/**
 * The stream is over and no closing event came. Every turn the server reads to its end sends one
 * (`turn.completed` or `error`, crisis and "can't answer" turns included), so this means the
 * connection dropped. The live turn shows as stopped for every kind; the server's copy may say
 * otherwise (a crisis or "can't answer" turn keeps its own status), and replaces it when the
 * conversation is read again. The escalation panel still shows: the live turn draws a crisis or
 * unavailable escalation in any phase.
 */
function endWithoutClosingEvent(
  deps: Pick<SendDeps, 'invalidateConversation'>,
  origin: SendOrigin,
) {
  const { status, turn } = useChatStore.getState()
  if (turn === null || !isRunning({ status })) return
  if (turn.turnId === null) {
    // No event came, so there is no turn to show. If the server had answered (200) it holds the
    // question, and saves the turn stopped: the question is not an unsent draft any more (as
    // `turn.started` would have made it), and the conversation is read so the saved turn shows.
    // A resend would ask it twice. If it had not answered, nothing exists to read.
    useChatStore.setState((state) => ({
      status: 'idle',
      turn: null,
      sendError: conversationCopy.sendFailed,
      draft:
        turn.accepted && origin === 'composer' && trimLikePython(state.draft) === turn.question
          ? ''
          : state.draft,
    }))
    if (turn.accepted) deps.invalidateConversation()
    return
  }
  // (An `error` event has already put the turn in `error`, which returned above.)
  useChatStore.setState({
    status: 'stopped',
    turn: { ...turn, steps: allDone(turn.steps), completed: false },
    sendError: null,
  })
  deps.invalidateConversation()
}

/** How a finished turn is shown while it waits for its saved copy. */
function finishedPhase(status: ChatStatus): SettlingTurn['phase'] {
  return status === 'error' || status === 'stopped' ? status : 'idle'
}

/** The send did not go through. The draft stays, and the person is told why. */
function failSend(error: unknown, deps: SendDeps) {
  const cleared = { status: 'idle', turn: null } as const
  const set = useChatStore.setState
  if (!(error instanceof ApiError)) {
    set({ ...cleared, sendError: conversationCopy.sendFailed })
    return
  }
  const type = error.problem?.type
  if (error.status === 409 && type === 'turn-running') {
    // Keep saying "still answering", and read the conversation so the running turn shows and the
    // poller picks it up.
    deps.invalidateConversation()
    set({ ...cleared, sendError: deps.texts.stillAnswering })
  } else if (error.status === 409 && type === 'conversation-unreadable') {
    // Read the conversation again: it comes back `unreadable`, with no turns, and the notice says
    // why in the owner's words. No line under the box too, which would say it twice.
    deps.invalidateConversation()
    set({ ...cleared, offerNewConversation: true })
  } else if (
    error.status === 409 &&
    (type === 'conversation-outdated' || type === 'history-too-long')
  ) {
    set({ ...cleared, sendError: problemText(error), offerNewConversation: true })
  } else if (error.status === 429 && type === 'budget-conversation') {
    // Only this conversation's size is the problem: a new one would fit in what is left. Nothing
    // on the page said so before the send (the banner shows only a spent sandbox), so the
    // problem's words and the notice's button come from this refusal, as for a conversation that
    // can't continue. The read refreshes the budget.
    deps.invalidateConversation()
    set({
      ...cleared,
      sendError: problemText(error),
      offerNewConversation: true,
      offerWithoutNoticeWords: true,
    })
  } else if (error.status === 422 && type === 'personal-data') {
    set({ ...cleared, warning: deps.texts.personalData })
  } else if (error.status === 429 && type !== undefined && BUDGET_CODES.has(type)) {
    // The banner comes from the conversation read. Its "reached" is sized for the smallest
    // question, while this refusal sized the real one plus the history, so a long question can be
    // refused with no banner: the problem's words go under the box. When the banner does show, the
    // composer's budget line wins there, so it is still one message.
    deps.invalidateConversation()
    set({ ...cleared, sendError: problemText(error) })
  } else if (error.status === 404) {
    // The conversation it was sent to is gone (or was never this person's): forget it, so the
    // next question uses the server's current one.
    // Its turns that were waiting for a saved copy belonged to the old conversation, so they go.
    set({ ...cleared, conversationId: null, settling: [], sendError: conversationCopy.sendFailed })
    deps.forgetConversation()
  } else {
    if (error.status === 401) deps.onUnauthorized()
    set({ ...cleared, sendError: problemText(error) })
  }
}

registerReset(() => {
  generation++
  epoch++
  inFlight?.abort()
  inFlight = null
  useChatStore.setState(EMPTY)
})
