import { memo, useContext, type ReactNode } from 'react'
import type { CitationOut, HrContactOut, TurnOut } from '@/api/generated'
import { CitationMarker } from '@/components/assistant/citation-marker'
import { ApiError } from '@/lib/api-fetch'
import {
  AssistantMessage,
  type AssistantMessageProps,
  type AssistantMessageStatus,
} from '@/components/assistant/assistant-message'
import { EscalationPanel } from '@/components/assistant/escalation-panel'
import { AnswerFooter, Feedback } from '@/components/assistant/feedback'
import { HrContacts } from '@/components/assistant/hr-contacts'
import { conversationCopy } from '@/components/assistant/labels'
import { SourceChips } from '@/components/assistant/source-chip'
import type { StatusStep } from '@/components/assistant/status-line'
import { UserMessage } from '@/components/assistant/user-message'
import { WorkTrace } from '@/components/assistant/work-trace'
import { OpenSourceContext } from './open-source'
import { withSourceKeys } from './source-key'
import type { LiveTurn } from './store'
import { useAssistantTexts, useFeedback } from './use-conversation'

// One question and its answer, as the conversation page draws it: the stored turns from the
// server, and the live one from the chat store. Each is composed the way the gallery's
// `Conversation` states are (app/gallery/sections/conversation-sections.tsx).

/** What every turn needs from the page. */
export type TurnContext = {
  /** The HR people a not-found answer's card lists. */
  hrContacts: HrContactOut[]
  /** The marker for a citation: stable, so a memoized answer is not drawn again for nothing. */
  renderMarker: (citation: CitationOut) => ReactNode
  /** Opens the passage a marker or chip cites, or closes it if it is the open one. */
  onOpenSource: (citation: CitationOut) => void
  /** Sends a question again (Retry, Ask again, Try again). */
  onAskAgain: (question: string) => void
  /** A budget banner is up, so the composer is off and Retry would only fail again. */
  budgetStop: boolean
}

/** A marker that knows whether its passage is the open one, from `OpenSourceContext`. */
export function SourceMarker({
  citation,
  onOpen,
}: {
  citation: CitationOut
  onOpen: (citation: CitationOut) => void
}) {
  const openKey = useContext(OpenSourceContext)
  return (
    <CitationMarker citation={citation} expanded={citation.passageId === openKey} onOpen={onOpen} />
  )
}

/** The source chips, with the open passage taken from `OpenSourceContext`. */
function OpenAwareChips({
  citations,
  onOpen,
}: {
  citations: CitationOut[]
  onOpen: (citation: CitationOut) => void
}) {
  const openKey = useContext(OpenSourceContext)
  return <SourceChips citations={citations} openPassageId={openKey} onOpen={onOpen} />
}

type MessageProps = {
  status: AssistantMessageStatus
  errorMessage?: string
  text: string
  citations: CitationOut[]
  steps?: StatusStep[]
  onAskAgain?: () => void
  onRetry?: () => void
  contacts?: ReactNode
  footer?: ReactNode
  context: TurnContext
}

/** The assistant's message with the page's marker and chips. */
function Message({ status, errorMessage, citations, context, footer, ...rest }: MessageProps) {
  const shared = {
    ...rest,
    citations,
    renderMarker: context.renderMarker,
    sources:
      citations.length > 0 ? (
        <OpenAwareChips citations={citations} onOpen={context.onOpenSource} />
      ) : undefined,
    feedback: footer,
  }
  // The type wants an error message exactly when the status is `error`.
  const props: AssistantMessageProps =
    status === 'error'
      ? { ...shared, status, errorMessage: errorMessage ?? conversationCopy.sendFailed }
      : { ...shared, status }
  return <AssistantMessage {...props} />
}

/** "Was this right?" for a stored answer. One mutation per turn, so two turns never share a state. */
function TurnFeedback({ turn }: { turn: TurnOut }) {
  const give = useFeedback()
  const { data: texts } = useAssistantTexts()
  const error = give.error
  // The API takes one answer per turn: a 409 means it already has one.
  const already = error instanceof ApiError && error.status === 409
  const sent = turn.feedback !== null || give.isSuccess || already
  const onSubmit: Parameters<typeof Feedback>[0]['onSubmit'] = (feedback) =>
    give.mutate({ turnId: turn.id, data: feedback })
  if (sent) return <Feedback status="sent" onSubmit={onSubmit} />
  if (give.isPending) return <Feedback status="sending" onSubmit={onSubmit} />
  if (error instanceof ApiError) {
    // A reason that looks like a Social Security or card number is refused with the API's own words,
    // which the page fetched up front. What was typed stays in the box.
    const personalData = error.status === 422 && error.problem?.type === 'personal-data'
    const message = personalData
      ? (texts?.personalData ?? conversationCopy.sendFailed)
      : error.problem?.detail || conversationCopy.sendFailed
    return <Feedback status="error" errorMessage={message} onSubmit={onSubmit} />
  }
  return <Feedback status="idle" onSubmit={onSubmit} />
}

function trace(turn: TurnOut, citations: CitationOut[]) {
  return (
    <WorkTrace
      guard={turn.guard}
      toolCalls={turn.toolCalls}
      sections={turn.sections}
      citations={citations}
    />
  )
}

/**
 * A turn that finished and was saved. Memoized: while a later answer streams, the page draws again
 * for every piece of text, and the turns before it have not changed (the turn and the context are
 * the same objects until the conversation is read again), so they stay as they are.
 */
export const StoredTurn = memo(function StoredTurn({
  turn,
  context,
}: {
  turn: TurnOut
  context: TurnContext
}) {
  const citations = withSourceKeys(turn.citations)
  const escalation = turn.escalation
  const again = () => context.onAskAgain(turn.question)
  // A sensitive turn shows its HR panel whatever became of the answer (it can fail, or be cut
  // off): sensitive topics go to a person. Keyed by the turn, and a saved panel never announces.
  const panel =
    escalation === null ? null : (
      <EscalationPanel
        key={`escalation-${turn.id}`}
        kind={escalation.kind}
        message={escalation.message}
        contacts={escalation.hrContact}
      />
    )

  // A crisis or "can't answer right now" never reached the model: the panel alone follows the
  // question.
  if (escalation?.kind === 'crisis' || escalation?.kind === 'unavailable') {
    return (
      <>
        <UserMessage text={turn.question} />
        <EscalationPanel
          key={`escalation-${turn.id}`}
          kind={escalation.kind}
          message={escalation.message}
          contacts={escalation.hrContact}
          onTryAgain={escalation.kind === 'unavailable' ? again : undefined}
        />
      </>
    )
  }

  if (turn.status === 'stopped') {
    return (
      <>
        <UserMessage text={turn.question} />
        <Message
          status="stopped"
          text={turn.answerText}
          citations={citations}
          onAskAgain={again}
          context={context}
        />
        {panel}
      </>
    )
  }
  if (turn.status === 'failed') {
    return (
      <>
        <UserMessage text={turn.question} />
        <Message
          status="error"
          errorMessage={turn.error?.message}
          text={turn.answerText}
          citations={citations}
          onRetry={context.budgetStop ? undefined : again}
          context={context}
        />
        {panel}
      </>
    )
  }
  if (turn.status === 'running') {
    // Seen only from a reload while the server is still answering: the question, and whatever of
    // the answer has been saved. Sending another question gets the API's "still answering".
    return (
      <>
        <UserMessage text={turn.question} />
        <Message
          status="streaming"
          text={turn.answerText}
          citations={citations}
          context={context}
        />
        {panel}
      </>
    )
  }

  const status = turn.incomplete ? 'incomplete' : 'complete'
  if (escalation?.kind === 'sensitive') {
    // The assistant's answer, then the fixed panel, then "Show your work" under the panel, kept to
    // the assistant message's 680 px (the Build decisions in notes.md).
    return (
      <>
        <UserMessage text={turn.question} />
        <Message
          status={status}
          text={turn.answerText}
          citations={citations}
          footer={<AnswerFooter feedback={<TurnFeedback turn={turn} />} work={null} />}
          context={context}
        />
        <EscalationPanel
          key={`escalation-${turn.id}`}
          kind="sensitive"
          message={escalation.message}
          contacts={escalation.hrContact}
        />
        <div className="max-w-[680px]">
          <AnswerFooter work={trace(turn, citations)} />
        </div>
      </>
    )
  }
  return (
    <>
      <UserMessage text={turn.question} />
      <Message
        status={status}
        text={turn.answerText}
        citations={citations}
        contacts={
          turn.notFound ? <HrContacts variant="card" contacts={context.hrContacts} /> : undefined
        }
        footer={
          <AnswerFooter feedback={<TurnFeedback turn={turn} />} work={trace(turn, citations)} />
        }
        context={context}
      />
    </>
  )
})

/**
 * The turn being answered now, or one that just finished and whose saved copy has not arrived.
 * `phase` is the store's status. Chips and feedback wait for the saved copy (the trace and the
 * feedback need what the server stored), so a finished live turn shows its text and sources.
 */
export function LiveTurnView({
  live,
  phase,
  context,
  settling = false,
}: {
  live: LiveTurn
  phase: 'sending' | 'streaming' | 'idle' | 'error' | 'stopped'
  context: TurnContext
  /** A finished turn waiting for its saved copy behind a newer one: its panel already announced. */
  settling?: boolean
}) {
  const citations = withSourceKeys(live.citations)
  const escalation = live.escalation
  const again = () => context.onAskAgain(live.question)

  const panel =
    escalation !== null ? (
      // Keyed by the turn, so each turn's panel is its own and announces its own arrival. Only a
      // panel that came down the stream announces (`live`), never one read back from the server.
      <EscalationPanel
        key={`escalation-${live.turnId ?? 'pending'}`}
        kind={escalation.kind}
        message={escalation.message}
        contacts={escalation.hrContact}
        onTryAgain={escalation.kind === 'unavailable' ? again : undefined}
        announceOnMount={escalation.live && !settling}
      />
    ) : null

  if (escalation?.kind === 'crisis' || escalation?.kind === 'unavailable') {
    return (
      <>
        <UserMessage text={live.question} />
        {panel}
      </>
    )
  }

  const status: AssistantMessageStatus =
    phase === 'error'
      ? 'error'
      : phase === 'stopped'
        ? 'stopped'
        : phase === 'idle'
          ? live.incomplete
            ? 'incomplete'
            : 'complete'
          : 'streaming'
  return (
    <>
      <UserMessage text={live.question} />
      <Message
        status={status}
        errorMessage={live.error?.message}
        text={live.text}
        citations={citations}
        steps={live.steps}
        onAskAgain={phase === 'stopped' ? again : undefined}
        onRetry={phase === 'error' && !context.budgetStop ? again : undefined}
        context={context}
      />
      {panel}
    </>
  )
}
