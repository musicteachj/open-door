import { useRef, useState, type ReactNode } from 'react'
import type { CitationOut } from '@/api/generated'
import { AssistantMessage } from '@/components/assistant/assistant-message'
import { BudgetBanner } from '@/components/assistant/budget-banner'
import { CitationMarker } from '@/components/assistant/citation-marker'
import { Composer, type ComposerProps } from '@/components/assistant/composer'
import { ConversationHeader, RetentionLine } from '@/components/assistant/conversation-header'
import { EscalationPanel } from '@/components/assistant/escalation-panel'
import { AnswerFooter, Feedback } from '@/components/assistant/feedback'
import { HrContacts } from '@/components/assistant/hr-contacts'
import { conversationCopy } from '@/components/assistant/labels'
import { SourceChips } from '@/components/assistant/source-chip'
import type { StatusStep } from '@/components/assistant/status-line'
import { UserMessage } from '@/components/assistant/user-message'
import { WorkTrace } from '@/components/assistant/work-trace'
import { PassagePanel } from '@/components/handbook/passage-panel'
import { SandboxIndicator } from '@/components/status/sandbox-indicator'
import { Group, Section } from '../gallery-parts'
import {
  BUDGET_DAILY_TEXT,
  BUDGET_SANDBOX_TEXT,
  CRISIS_QUESTION,
  CRISIS_TEXT,
  DANA,
  ERROR_INTERNAL_TEXT,
  LENGTH_HINT_DRAFT,
  LONG_TURNS,
  NOT_FOUND_TURN,
  OTHER_STATE_TURN,
  PERSONAL_DATA_DRAFT,
  PERSONAL_DATA_TEXT,
  REFUSAL_TURN,
  SENSITIVE_TEXT,
  SENSITIVE_TURN,
  SICK_ERROR_CITATIONS,
  SICK_ERROR_TEXT,
  SICK_PASSAGE_VIEWS,
  SICK_STOPPED_CITATIONS,
  SICK_STOPPED_TEXT,
  SICK_STREAMING_CITATIONS,
  SICK_STREAMING_TEXT,
  SICK_TURN,
  STILL_ANSWERING_TEXT,
  UNAVAILABLE_TEXT,
  type SampleTurn,
} from './conversation-fixtures'

// The conversation view's states from docs/design/screens/07-conversation/notes.md, one section for
// each row of its States table and in its order, built from the real components with the design's
// sample answers. Each state is composed the way the conversation page will compose it (Stage 6):
// the header row, the thread at the 760 px measure, and the docked composer. Hover and focus are
// not drawn: the tests hover and focus the real elements. The pieces that hold state in the app
// (the reason form, "Show your work", the composer) hold it here too, so they can be used.
//
// The source panel starts closed, as the handbook's does: an open panel moves focus to its title,
// and that must not happen on page load. Pressing a marker opens it.

const noop = () => {}

// ----- The frame -----

/**
 * One state as the page shows it: an optional banner across the top, the header row, the thread,
 * and the composer, in a column at the 760 px measure. The state is one wrapper that breaks out of
 * the gallery's 760 px column, centered on it, so the frame is 810 px wide (a 760 px column inside
 * 24 px of padding and a 1 px border each side), and never wider than the window. Every state
 * has this width. The source panel, when it is open, sits in
 * its own 420 px frame below the conversation frame, on its left edge: the design docks it beside
 * the column, which Stage 6's captures of the real page check.
 */
function Conversation({
  banner,
  panel,
  composer,
  children,
}: {
  banner?: ReactNode
  panel?: ReactNode
  composer: ReactNode
  children: ReactNode
}) {
  return (
    <div
      data-slot="conversation-state"
      className="relative left-1/2 flex w-[min(810px,calc(100vw-4rem))] shrink-0 -translate-x-1/2 flex-col gap-6"
    >
      <div
        data-slot="conversation-frame"
        className="flex w-full flex-col overflow-hidden rounded-lg border border-border bg-surface-raised"
      >
        {banner}
        <div className="flex w-full flex-col gap-6 p-4 sm:p-6">
          <div className="flex w-full max-w-content min-w-0 flex-col gap-6">
            <ConversationHeader onNewConversation={noop}>
              <SandboxIndicator>Sandbox resets in 21 h</SandboxIndicator>
            </ConversationHeader>
            <div data-slot="conversation-thread" className="flex min-w-0 flex-col gap-6">
              {children}
            </div>
            {composer}
            <RetentionLine className="sm:hidden" />
          </div>
        </div>
      </div>
      {panel}
    </div>
  )
}

/** The composer, holding its draft as the page's store does. */
function ThreadComposer({ initial = '', ...props }: { initial?: string } & Partial<ComposerProps>) {
  const [value, setValue] = useState(initial)
  return (
    <Composer
      value={value}
      onChange={setValue}
      onSubmit={noop}
      variant="docked"
      placeholder={conversationCopy.followUpPlaceholder}
      {...props}
    />
  )
}

// ----- The messages -----

/** "Was this right?" with its own state: a send is answered as the API would, with a thank-you. */
function LiveFeedback({
  initial = 'idle',
  defaultOpen,
  defaultReason,
}: {
  initial?: 'idle' | 'sent'
  defaultOpen?: boolean
  defaultReason?: string
}) {
  const [status, setStatus] = useState(initial)
  return (
    <Feedback
      status={status}
      defaultOpen={defaultOpen}
      defaultReason={defaultReason}
      onSubmit={() => setStatus('sent')}
    />
  )
}

/** The marker the page passes the answer: active while its passage is the one in the panel. */
const markerFor =
  (openPassageId: string | null, onOpen: (citation: CitationOut) => void) =>
  (citation: CitationOut) => (
    <CitationMarker
      citation={citation}
      expanded={citation.passageId === openPassageId}
      onOpen={onOpen}
    />
  )

function Trace({ turn, open = false }: { turn: SampleTurn; open?: boolean }) {
  return (
    <WorkTrace
      guard={turn.guard}
      toolCalls={turn.toolCalls}
      sections={turn.sections}
      citations={turn.citations}
      defaultOpen={open}
    />
  )
}

type FeedbackSetup = Parameters<typeof LiveFeedback>[0]

/** A finished answer with its slots filled: sources, the footer, and the HR contacts if any. */
function Answer({
  turn,
  feedback,
  traceOpen = false,
  contacts,
  openPassageId = null,
  onOpen = noop,
}: {
  turn: SampleTurn
  feedback?: FeedbackSetup
  traceOpen?: boolean
  contacts?: ReactNode
  openPassageId?: string | null
  onOpen?: (citation: CitationOut) => void
}) {
  return (
    <AssistantMessage
      status="complete"
      text={turn.text}
      citations={turn.citations}
      renderMarker={markerFor(openPassageId, onOpen)}
      sources={
        <SourceChips citations={turn.citations} openPassageId={openPassageId} onOpen={onOpen} />
      }
      contacts={contacts}
      feedback={
        <AnswerFooter
          feedback={<LiveFeedback {...feedback} />}
          work={<Trace turn={turn} open={traceOpen} />}
        />
      }
    />
  )
}

/** One question and its finished answer. */
function Turn(props: Parameters<typeof Answer>[0]) {
  return (
    <>
      <UserMessage text={props.turn.question} />
      <Answer {...props} />
    </>
  )
}

/**
 * A sensitive turn: the assistant's answer, then the fixed panel, then "Show your work" under the
 * panel (the Build decisions in notes.md). The panel has no "Was this right?"; the answer above it
 * has.
 */
function SensitiveTurn({ traceOpen = false }: { traceOpen?: boolean }) {
  const turn = SENSITIVE_TURN
  return (
    <>
      <UserMessage text={turn.question} />
      <AssistantMessage
        status="complete"
        text={turn.text}
        citations={turn.citations}
        renderMarker={markerFor(null, noop)}
        sources={<SourceChips citations={turn.citations} onOpen={noop} />}
        feedback={<AnswerFooter feedback={<LiveFeedback />} work={null} />}
      />
      <EscalationPanel kind="sensitive" message={SENSITIVE_TEXT} contacts={[DANA]} />
      {/* Under the panel, "Show your work" keeps the assistant message's 680 px cap. */}
      <div className="max-w-[680px]">
        <AnswerFooter work={<Trace turn={turn} open={traceOpen} />} />
      </div>
    </>
  )
}

const SEARCHING: StatusStep[] = [{ id: 'search', text: 'Searching the handbook…', done: false }]
const SEARCHING_AGAIN: StatusStep[] = [
  { id: 'searched', text: 'Searched the handbook: sick leave', done: true },
  // The design's "Read §4.3 Sick leave" matches no tool event, so only this fixture shows it.
  { id: 'read', text: 'Read §4.3 Sick leave', done: true },
  { id: 'again', text: 'Searching the handbook again…', done: false },
]

// ----- The states that hold something of their own -----

/** The source panel's state: pressing a marker or a chip opens that passage in its own frame below. */
function SourcePanelState() {
  const [open, setOpen] = useState<CitationOut | null>(null)
  const opener = useRef<HTMLElement | null>(null)
  const onOpen = (citation: CitationOut) => {
    if (open?.passageId === citation.passageId) return close()
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    setOpen(citation)
  }
  function close() {
    setOpen(null)
    // Focus returns after the panel unmounts, to the marker or chip that opened it.
    queueMicrotask(() => opener.current?.focus())
  }
  const view = open ? SICK_PASSAGE_VIEWS[open.passageId] : undefined
  return (
    <Conversation
      composer={<ThreadComposer />}
      panel={
        open &&
        view && (
          <div
            data-slot="source-panel-frame"
            className="h-[640px] w-[420px] max-w-full self-start overflow-hidden rounded-lg border border-border bg-surface-raised"
          >
            <PassagePanel
              state="open"
              sectionId={open.sectionId}
              passageId={view.passage.id}
              view={view}
              onClose={close}
            />
          </div>
        )
      }
    >
      <Turn turn={SICK_TURN} openPassageId={open?.passageId ?? null} onOpen={onOpen} />
    </Conversation>
  )
}

/**
 * A question sent while an answer streams. Stop ends the stream at once, and the draft stays in
 * the box. `data-submit-count` counts what the form sent: it stays 0, because Stop is not Ask. The
 * browser test reads it.
 */
function SendErrorState() {
  const [streaming, setStreaming] = useState(true)
  const [submits, setSubmits] = useState(0)
  return (
    <div data-submit-count={submits} className="w-full">
      <Conversation
        composer={
          <ThreadComposer
            initial="Can I carry unused days over?"
            streaming={streaming}
            onStop={() => setStreaming(false)}
            onSubmit={() => setSubmits((count) => count + 1)}
            sendError={streaming ? STILL_ANSWERING_TEXT : undefined}
          />
        }
      >
        <UserMessage text={SICK_TURN.question} />
        <AssistantMessage
          status={streaming ? 'streaming' : 'stopped'}
          text={SICK_STREAMING_TEXT}
          citations={SICK_STREAMING_CITATIONS}
          renderMarker={markerFor(null, noop)}
          onAskAgain={noop}
        />
      </Conversation>
    </div>
  )
}

export function ConversationSections() {
  return (
    <Group title="Conversation">
      <Section id="conversation-cited-answer" title="Cited answer, with the docked composer">
        <Conversation composer={<ThreadComposer />}>
          <Turn turn={SICK_TURN} />
        </Conversation>
      </Section>
      <Section id="conversation-source-panel" title="Source panel, opened from a marker">
        <SourcePanelState />
      </Section>
      <Section id="conversation-streaming-searching" title="Streaming, searching">
        <Conversation composer={<ThreadComposer streaming />}>
          <UserMessage text={SICK_TURN.question} />
          <AssistantMessage
            status="streaming"
            text=""
            steps={SEARCHING}
            renderMarker={markerFor(null, noop)}
          />
        </Conversation>
      </Section>
      <Section id="conversation-streaming-text" title="Streaming, text arriving">
        <Conversation composer={<ThreadComposer streaming />}>
          <UserMessage text={SICK_TURN.question} />
          <AssistantMessage
            status="streaming"
            text={SICK_STREAMING_TEXT}
            citations={SICK_STREAMING_CITATIONS}
            renderMarker={markerFor(null, noop)}
          />
        </Conversation>
      </Section>
      <Section
        id="conversation-streaming-progress-note"
        title="Streaming, the draft replaced by a status line while it searches again"
      >
        <Conversation composer={<ThreadComposer streaming />}>
          <UserMessage text={SICK_TURN.question} />
          <AssistantMessage
            status="streaming"
            text=""
            steps={SEARCHING_AGAIN}
            renderMarker={markerFor(null, noop)}
          />
        </Conversation>
      </Section>
      <Section id="conversation-stopped" title="Stopped, with Ask again">
        <Conversation composer={<ThreadComposer />}>
          <UserMessage text={SICK_TURN.question} />
          <AssistantMessage
            status="stopped"
            text={SICK_STOPPED_TEXT}
            citations={SICK_STOPPED_CITATIONS}
            renderMarker={markerFor(null, noop)}
            onAskAgain={noop}
          />
        </Conversation>
      </Section>
      <Section id="conversation-show-your-work" title="Show your work, expanded">
        <Conversation composer={<ThreadComposer />}>
          <Turn turn={SICK_TURN} traceOpen />
        </Conversation>
      </Section>
      <Section
        id="conversation-show-your-work-routed"
        title="Show your work, expanded on a sensitive turn (routed to HR guidance)"
      >
        <Conversation composer={<ThreadComposer />}>
          <SensitiveTurn traceOpen />
        </Conversation>
      </Section>
      <Section id="conversation-feedback-yes" title="Feedback, Yes and the thank-you line">
        <Conversation composer={<ThreadComposer />}>
          <Turn turn={SICK_TURN} feedback={{ initial: 'sent' }} />
        </Conversation>
      </Section>
      <Section id="conversation-feedback-no" title="Feedback, No with the reason form">
        <Conversation composer={<ThreadComposer />}>
          <Turn
            turn={SICK_TURN}
            feedback={{
              defaultOpen: true,
              defaultReason: "It didn't say whether I need a doctor's note.",
            }}
          />
        </Conversation>
      </Section>
      <Section id="conversation-feedback-thanks" title="Feedback, the thank-you after a reason">
        <Conversation composer={<ThreadComposer />}>
          <Turn turn={SICK_TURN} feedback={{ initial: 'sent' }} />
        </Conversation>
      </Section>
      <Section id="conversation-other-state" title="Another state's policy, as Mateo">
        <Conversation composer={<ThreadComposer />}>
          <Turn turn={OTHER_STATE_TURN} />
        </Conversation>
      </Section>
      <Section id="conversation-not-found" title="Not in the handbook, with the HR contacts">
        <Conversation composer={<ThreadComposer />}>
          <Turn turn={NOT_FOUND_TURN} contacts={<HrContacts variant="card" contacts={[DANA]} />} />
        </Conversation>
      </Section>
      <Section id="conversation-refusal" title="Refusal, another employee's home address">
        <Conversation composer={<ThreadComposer />}>
          <Turn turn={REFUSAL_TURN} />
        </Conversation>
      </Section>
      <Section id="conversation-sensitive" title="Sensitive, the answer then the HR panel">
        <Conversation composer={<ThreadComposer />}>
          <SensitiveTurn />
        </Conversation>
      </Section>
      <Section id="conversation-crisis" title="Crisis panel">
        <Conversation composer={<ThreadComposer />}>
          <UserMessage text={CRISIS_QUESTION} />
          <EscalationPanel kind="crisis" message={CRISIS_TEXT} contacts={[DANA]} />
        </Conversation>
      </Section>
      <Section id="conversation-error-midstream" title="Error inside the assistant's message">
        <Conversation composer={<ThreadComposer />}>
          <UserMessage text={SICK_TURN.question} />
          <AssistantMessage
            status="error"
            // The API's own text for this failure (ERROR_TEXTS["internal"]).
            errorMessage={ERROR_INTERNAL_TEXT}
            text={SICK_ERROR_TEXT}
            citations={SICK_ERROR_CITATIONS}
            renderMarker={markerFor(null, noop)}
            onRetry={noop}
          />
        </Conversation>
      </Section>
      <Section id="conversation-cant-answer" title="Can't answer right now">
        <Conversation composer={<ThreadComposer />}>
          <UserMessage text={SICK_TURN.question} />
          <EscalationPanel
            kind="unavailable"
            message={UNAVAILABLE_TEXT}
            contacts={[DANA]}
            onTryAgain={noop}
          />
        </Conversation>
      </Section>
      <Section id="conversation-send-error" title="Send error while an answer is streaming">
        <SendErrorState />
      </Section>
      <Section
        id="conversation-budget-sandbox"
        title="Budget banner, this sandbox's budget is used"
      >
        <Conversation
          banner={
            <BudgetBanner kind="sandbox" message={BUDGET_SANDBOX_TEXT} onStartNewSandbox={noop} />
          }
          composer={<ThreadComposer disabledReason="sandbox" />}
        >
          <Turn turn={SICK_TURN} />
        </Conversation>
      </Section>
      <Section id="conversation-budget-daily" title="Budget banner, today's demo budget is reached">
        <Conversation
          banner={<BudgetBanner kind="daily" message={BUDGET_DAILY_TEXT} />}
          composer={<ThreadComposer disabledReason="daily" />}
        >
          <Turn turn={SICK_TURN} />
        </Conversation>
      </Section>
      <Section id="conversation-length-hint" title="Length hint near 2,000 characters">
        <Conversation composer={<ThreadComposer initial={LENGTH_HINT_DRAFT} />}>
          <Turn turn={SICK_TURN} />
        </Conversation>
      </Section>
      <Section id="conversation-personal-data" title="Personal-data warning">
        <Conversation
          composer={<ThreadComposer initial={PERSONAL_DATA_DRAFT} warning={PERSONAL_DATA_TEXT} />}
        >
          <Turn turn={SICK_TURN} />
        </Conversation>
      </Section>
      <Section id="conversation-long-conversation" title="Long-conversation notice">
        <Conversation composer={<ThreadComposer longConversation onNewConversation={noop} />}>
          {LONG_TURNS.map((turn) => (
            <Turn key={turn.question} turn={turn} />
          ))}
        </Conversation>
      </Section>
    </Group>
  )
}
