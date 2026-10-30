import { memo, useContext, type ReactNode } from 'react'
import type { CitationOut, EscalationOut, HrContactOut, TurnOut } from '@/api/generated'
import { CitationMarker } from '@/components/assistant/citation-marker'
import { ApiError } from '@/lib/api-fetch'
import type { PageLink } from '@/lib/page-link'
import {
  AssistantMessage,
  type AssistantMessageProps,
  type AssistantMessageStatus,
} from '@/components/assistant/assistant-message'
import { CasePanel } from '@/features/cases/case-panel'
import { AnswerFooter, Feedback } from '@/components/assistant/feedback'
import { HrContacts } from '@/components/assistant/hr-contacts'
import { conversationCopy } from '@/components/assistant/labels'
import { SourceChips } from '@/components/assistant/source-chip'
import type { StatusStep } from '@/components/assistant/status-line'
import { UserMessage } from '@/components/assistant/user-message'
import { WorkTrace } from '@/components/assistant/work-trace'
import { OpenSourceContext } from './open-source'
import { withSourceKeys } from './source-key'
import { ProposalCards } from './proposal-cards'
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
  /** "Write to HR" after the HR contacts. Null for HR, who has no My cases page. */
  writeToHr: PageLink | null
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

/**
 * Whether a saved turn may offer a case: it has ended, whatever became of its answer (it can fail
 * or be stopped), except after an internal error, when the server may not have stored its verdict.
 */
function caseOffered(turn: TurnOut): boolean {
  if (turn.status === 'running') return false
  return !(turn.status === 'failed' && turn.error?.code === 'internal')
}

/**
 * A stored turn's HR panel, with its case offer. A saved panel never announces. The offer needs a
 * turn that is not still running and did not fail with an internal error (a turn that failed in
 * another way is still offered).
 */
function storedPanel(
  turn: TurnOut,
  escalation: EscalationOut,
  writeToHr: PageLink | null,
  onTryAgain?: () => void,
) {
  return (
    <CasePanel
      key={`escalation-${turn.id}`}
      kind={escalation.kind}
      message={escalation.message}
      contacts={escalation.hrContact}
      onTryAgain={onTryAgain}
      writeToHr={writeToHr}
      turnId={turn.id}
      question={turn.question}
      ended={caseOffered(turn)}
      offerCase={escalation.offerCase}
      caseOpened={turn.caseOpened}
    />
  )
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
  // The HR contacts card of a not-found answer, whatever else the turn made, so no branch below
  // can leave it out.
  const notFoundContacts = turn.notFound ? (
    <HrContacts variant="card" contacts={context.hrContacts} writeToHr={context.writeToHr} />
  ) : undefined
  // The confirm cards the turn made, under its message. A card whose turn did not finish is
  // already canceled in the saved copy, and shows that.
  const cards = <ProposalCards proposals={turn.proposals} question={turn.question} />
  // Under a budget stop the server refuses every question, so there is nothing to ask again.
  const again = context.budgetStop ? undefined : () => context.onAskAgain(turn.question)
  // A sensitive turn shows its HR panel whatever became of the answer (it can fail, or be cut
  // off): sensitive topics go to a person. Keyed by the turn, and a saved panel never announces.
  // A "can't answer right now" panel can try again; a crisis one has nothing to retry.
  const panel =
    escalation === null
      ? null
      : storedPanel(
          turn,
          escalation,
          context.writeToHr,
          escalation.kind === 'unavailable' ? again : undefined,
        )

  // A crisis or "can't answer right now" never reached the model: the panel alone follows the
  // question.
  if (escalation?.kind === 'crisis' || escalation?.kind === 'unavailable') {
    return (
      <>
        <UserMessage text={turn.question} />
        {panel}
      </>
    )
  }

  if (turn.status === 'stopped') {
    return (
      <>
        <UserMessage text={turn.question} />
        <Message
          contacts={notFoundContacts}
          status="stopped"
          text={turn.answerText}
          citations={citations}
          onAskAgain={again}
          context={context}
        />
        {cards}
        {panel}
      </>
    )
  }
  if (turn.status === 'failed') {
    return (
      <>
        <UserMessage text={turn.question} />
        <Message
          contacts={notFoundContacts}
          status="error"
          errorMessage={turn.error?.message}
          text={turn.answerText}
          citations={citations}
          onRetry={again}
          context={context}
        />
        {cards}
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
          contacts={notFoundContacts}
          status="streaming"
          text={turn.answerText}
          citations={citations}
          context={context}
        />
        {cards}
        {panel}
      </>
    )
  }

  const status = turn.incomplete ? 'incomplete' : 'complete'
  if (escalation?.kind === 'sensitive') {
    // The assistant's answer, then the cards, then the fixed panel with the thread's wider gap
    // before it, then "Show your work" under all of it, kept to the assistant message's 680 px
    // (the Build decisions in notes.md).
    return (
      <>
        <UserMessage text={turn.question} />
        <Message
          contacts={notFoundContacts}
          status={status}
          text={turn.answerText}
          citations={citations}
          footer={<AnswerFooter feedback={<TurnFeedback turn={turn} />} work={null} />}
          context={context}
        />
        {cards}
        {panel}
        <div className="max-w-[680px]">
          <AnswerFooter work={trace(turn, citations)} />
        </div>
      </>
    )
  }
  if (turn.proposals.length > 0) {
    // The card sits directly under the message, and the one footer row (feedback on the left,
    // "Show your work" on the right) goes under the card, as screen 10 draws it.
    return (
      <>
        <UserMessage text={turn.question} />
        <Message
          status={status}
          text={turn.answerText}
          citations={citations}
          contacts={notFoundContacts}
          context={context}
        />
        {cards}
        <div className="max-w-[680px]">
          <AnswerFooter feedback={<TurnFeedback turn={turn} />} work={trace(turn, citations)} />
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
        contacts={notFoundContacts}
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
  // A card waits for its turn: until the answer is complete, Confirm says so. After that the saved
  // copy (read again as the turn ends) takes over with the server's own word. A turn that failed
  // or was stopped is not being answered either, whatever the read says or whether it arrives.
  const answering =
    phase !== 'error' && phase !== 'stopped' && !(phase === 'idle' && live.completed)
  const cards = (
    <ProposalCards proposals={live.proposals} question={live.question} turnRunning={answering} />
  )
  // Under a budget stop the server refuses every question, so there is nothing to ask again.
  const again = context.budgetStop ? undefined : () => context.onAskAgain(live.question)

  const panel =
    escalation !== null ? (
      // Keyed by the turn, so each turn's panel is its own and announces its own arrival. Only a
      // panel that came down the stream announces (`live`), never one read back from the server.
      <CasePanel
        key={`escalation-${live.turnId ?? 'pending'}`}
        kind={escalation.kind}
        message={escalation.message}
        contacts={escalation.hrContact}
        onTryAgain={escalation.kind === 'unavailable' ? again : undefined}
        writeToHr={context.writeToHr}
        announceOnMount={escalation.live && !settling}
        turnId={live.turnId}
        question={live.question}
        // Never on a live turn: it is offered on the saved copy, once the verdict is stored.
        ended={false}
        offerCase={escalation.offerCase}
        caseOpened={null}
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
        onRetry={phase === 'error' ? again : undefined}
        context={context}
      />
      {cards}
      {panel}
    </>
  )
}
