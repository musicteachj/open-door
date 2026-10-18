import { RotateCcw, Square } from 'lucide-react'
import { useMemo, type ReactNode } from 'react'
import { InlineError } from '@/components/feedback/inline-error'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { Answer, type AnswerProps } from './answer'
import { conversationCopy } from './labels'
import { numberBySection } from './sources'
import { StatusLine, type StatusStep } from './status-line'

/** One empty array for every message with no citations, so a default does not defeat `useMemo`. */
const NO_CITATIONS: NonNullable<AnswerProps['citations']> = []

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
  /** The source chips. Shown once the answer is finished (`complete` or `incomplete`). */
  sources?: ReactNode
  /** The HR contacts card of a not-found answer, below the text and sources. */
  contacts?: ReactNode
  /** "Was this right?" and "Show your work". Shown once the answer is finished. */
  feedback?: ReactNode
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
    sources,
    contacts,
    feedback,
    className,
  } = props
  // Numbered once for a given set of citations, so the answer below can skip its own work too.
  const numbered = useMemo(() => numberBySection(citations), [citations])
  const streaming = status === 'streaming'
  const finished = status === 'complete' || status === 'incomplete'
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
      {streaming && <StatusLine steps={steps} />}
      {/* Always in the page, so a screen reader is already watching it when the answer arrives. It
          takes no room while empty (the negative margin cancels its gap). Only
          this is busy while it streams, so the finished answer is read once: the status line above
          is a live region of its own, and a busy ancestor could hold its steps back unspoken. */}
      <div
        data-slot="answer-live"
        aria-live="polite"
        aria-busy={streaming}
        className="empty:-mt-3.5"
      >
        {text !== '' && (
          <Answer
            text={text}
            // Markers show the section's number (the API's count passages), so a marker 1 and a
            // chip 1 are the same section. See `numberBySection`.
            citations={numbered}
            renderMarker={renderMarker}
            caret={streaming}
          />
        )}
      </div>
      {status === 'incomplete' && (
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
      {finished && sources}
      {finished && contacts}
      {finished && feedback}
    </div>
  )
}

export { AssistantMessage }
export type { AssistantMessageProps, AssistantMessageStatus }
