import { RotateCcw, Square } from 'lucide-react'
import { type ReactNode, useEffect, useMemo, useState } from 'react'
import { InlineError } from '@/components/feedback/inline-error'
import { WalkthroughLink } from '@/components/walkthrough/walkthrough-link'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { Answer, type AnswerProps } from './answer'
import { conversationCopy } from './labels'
import { StatusLine, type StatusStep } from './status-line'
import { useRevealedText } from './use-revealed-text'

/** One empty array for every message with no citations, so a default does not defeat memoizing. */
const NO_CITATIONS: NonNullable<AnswerProps['citations']> = []

/** How long a streaming message waits for its first text before it says it is still working. */
export const STILL_WORKING_AFTER_MS = 8000

/** The browser's own first step, shown until the server's first step arrives (ADR 0025). */
const READING_STEPS: StatusStep[] = [
  { id: 'reading', text: conversationCopy.readingQuestion, done: false },
]

/** The browser's step while the model works after its last finished step (ADR 0025). */
const WORKING_STEP: StatusStep = {
  id: 'working',
  text: conversationCopy.workingOnAnswer,
  done: false,
}

/**
 * The steps to show while a message streams, so there is never a silent wait. Until the server
 * sends a step, the browser shows "Reading your question…". When every step is done and no text
 * has come yet (the model is thinking again), it adds "Working on the answer…". These are added a
 * moment after streaming starts, each time it does (the live turn's message can be reused for the
 * next question), because a live region does not announce the text it is inserted with.
 */
function useShownSteps(
  steps: StatusStep[],
  streaming: boolean,
  hasText: boolean,
  justAsked: boolean,
): StatusStep[] {
  // Whether the status line has been in the page since this stream started.
  const [ready, setReady] = useState(false)
  if (!streaming && ready) setReady(false)
  useEffect(() => {
    if (!streaming) return
    const timer = setTimeout(() => setReady(true), 0)
    return () => clearTimeout(timer)
  }, [streaming])
  if (!streaming || !ready || hasText) return steps
  if (steps.length === 0) return justAsked ? READING_STEPS : [WORKING_STEP]
  if (steps.every((step) => step.done)) return [...steps, WORKING_STEP]
  return steps
}

/** True once a message has streamed for `STILL_WORKING_AFTER_MS` with no answer text. */
function useStillWorking(streaming: boolean, hasText: boolean): boolean {
  const [late, setLate] = useState(false)
  const waiting = streaming && !hasText
  // Each wait counts its own 8 seconds: text that arrives and is then taken back starts a new one.
  if (!waiting && late) setLate(false)
  useEffect(() => {
    if (!waiting) return
    const timer = setTimeout(() => setLate(true), STILL_WORKING_AFTER_MS)
    return () => clearTimeout(timer)
  }, [waiting])
  return waiting && late
}

/**
 * Where the message is. `incomplete` is a finished answer the output limit cut off. A not-found
 * answer and a refusal are ordinary `complete` answers: what makes them so is their words.
 */
type AssistantMessageStatus = 'streaming' | 'complete' | 'stopped' | 'incomplete' | 'error'

type AssistantMessageBaseProps = {
  /** The answer's Markdown, as far as it has arrived. */
  text: string
  citations?: AnswerProps['citations']
  renderMarker: AnswerProps['renderMarker']
  /** What the assistant is doing, shown while it streams. */
  steps?: StatusStep[]
  onAskAgain?: () => void
  onRetry?: () => void
  /** On an error: shows "Watch the recorded walkthrough" under the text (Phase 9a). */
  offerWalkthrough?: boolean
  /** The source chips. Shown once the answer is finished (`complete` or `incomplete`). */
  sources?: ReactNode
  /** The HR contacts card of a not-found answer, below the text and sources. */
  contacts?: ReactNode
  /** "Was this right?" and "Show your work". Shown once the answer is finished. */
  feedback?: ReactNode
  /** The turn's id, so the paced reveal carries on when the turn is drawn again (live to saved). */
  revealKey?: string | null
  /**
   * The question was just asked in this tab, so "Reading your question…" is true. False for a
   * running turn seen after a reload, which says "Working on the answer…" instead.
   */
  justAsked?: boolean
  className?: string
}

/**
 * An `error` message must carry the API's own text for the failure, shown verbatim and never
 * worded here, so the type refuses an error with none. Every other status takes no message.
 */
type AssistantMessageProps = AssistantMessageBaseProps &
  (
    | { status: 'error'; errorMessage: string }
    | { status: Exclude<AssistantMessageStatus, 'error'>; errorMessage?: undefined }
  )

/**
 * One assistant message (from the design's Conversation frames): no bubble, capped at 680 px,
 * and always started by the "AI" label and "Open Door", in every state, because the assistant
 * always says it is an AI (invariant 7). Its answer text is a polite live region that is
 * `aria-busy` while it streams, so the finished answer is read as a whole. The page (Stage 6) owns the
 * timing; this owns the markup. Sources, contacts, and feedback are slots the caller fills, and
 * only a finished answer shows them.
 */
function AssistantMessage(props: AssistantMessageProps) {
  const {
    status,
    text,
    citations = NO_CITATIONS,
    renderMarker,
    steps = [],
    onAskAgain,
    onRetry,
    offerWalkthrough = false,
    revealKey,
    justAsked = true,
    sources,
    contacts,
    feedback,
    className,
  } = props
  const streaming = status === 'streaming'
  // The text is played out at a steady pace while it streams, so a large piece never lands at once.
  // A stopped or failed answer shows what arrived at once, beside its "Stopped" line or error.
  const revealed = useRevealedText(
    text,
    streaming,
    status === 'stopped' || status === 'error',
    revealKey,
  )
  // A citation's marker shows once the text it follows has been revealed.
  const shownCitations = useMemo(
    () =>
      revealed.revealing
        ? citations.filter((citation) => citation.offsetUtf16 <= revealed.text.length)
        : citations,
    [citations, revealed.revealing, revealed.text.length],
  )
  const shownSteps = useShownSteps(steps, streaming, text !== '', justAsked)
  const stillWorking = useStillWorking(streaming, text !== '')
  // Nothing has arrived yet (no step, no text): the caret says the answer is on its way.
  const waiting = streaming && steps.length === 0
  // The footer waits for the last of the text, so it never sits above half-revealed words.
  const finished = (status === 'complete' || status === 'incomplete') && !revealed.revealing
  return (
    <div
      data-slot="assistant-message"
      className={cn('flex max-w-[680px] flex-col gap-3.5', className)}
    >
      <div className="flex items-center gap-2">
        <span className="inline-flex h-5 items-center rounded-xs border border-border-strong px-1.5 text-[11px]/4 font-semibold tracking-[0.03em] text-ink">
          {conversationCopy.aiLabel}
        </span>
        <span className="text-small text-ink-muted">{conversationCopy.assistantName}</span>
      </div>
      {streaming && (
        <StatusLine
          steps={shownSteps}
          hint={stillWorking ? conversationCopy.stillWorking : undefined}
        />
      )}
      {/* Always in the page, so a screen reader is already watching it when the answer arrives. It
          takes no room while empty (the negative margin cancels its gap). Only
          this is busy while it streams, so the finished answer is read once: the status line above
          is a live region of its own, and a busy ancestor could hold its steps back unspoken. */}
      <div
        data-slot="answer-live"
        aria-live="polite"
        aria-busy={streaming || revealed.revealing}
        // Text that has arrived and is still being played out: the thread follows its growth.
        data-revealing={revealed.revealing || undefined}
        className="empty:-mt-3.5"
      >
        {(revealed.text !== '' || waiting) && (
          <Answer
            text={revealed.text}
            // Already numbered by section where the citations entered the chat store or the
            // conversation query (`numberBySection`), so a marker 1 and a chip 1 are one section.
            citations={shownCitations}
            renderMarker={renderMarker}
            caret={streaming || revealed.revealing}
          />
        )}
      </div>
      {status === 'incomplete' && !revealed.revealing && (
        <p className="m-0 text-small text-ink-muted">{conversationCopy.incomplete}</p>
      )}
      {status === 'stopped' && (
        <div className="flex flex-wrap items-center gap-3">
          <output className="flex items-center gap-2 text-small font-semibold text-ink-muted">
            <Square aria-hidden="true" className="size-3.5" />
            {conversationCopy.stopped}
          </output>
          {onAskAgain && (
            <Button variant="secondary" size="sm" onClick={onAskAgain}>
              <RotateCcw aria-hidden="true" className="size-3.5" />
              {conversationCopy.askAgain}
            </Button>
          )}
        </div>
      )}
      {props.status === 'error' && (
        <InlineError
          message={props.errorMessage}
          onRetry={onRetry}
          inline
          className="mt-0 flex-wrap pr-0 pl-0"
        />
      )}
      {props.status === 'error' && offerWalkthrough && (
        // 8 px above, so its 24 px target circle clears the Retry button (WCAG 2.5.8).
        <span className="mt-2 block">
          <WalkthroughLink />
        </span>
      )}
      {finished && sources}
      {finished && contacts}
      {finished && feedback}
    </div>
  )
}

export { AssistantMessage }
export type { AssistantMessageProps, AssistantMessageStatus }
