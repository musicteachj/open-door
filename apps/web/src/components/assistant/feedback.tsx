import { CircleCheck } from 'lucide-react'
import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { InlineError } from '@/components/feedback/inline-error'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { REASON_LIMIT_CHARACTERS, conversationCopy } from './labels'
import { characterCount, trimLikePython } from './text-count'

/** What a person said about an answer. The reason is left out when the note is empty. */
type FeedbackSubmission = { helpful: true } | { helpful: false; reason?: string }

type FeedbackBaseProps = {
  /** Called with the answer to send. The caller sends it and then moves `status` on. */
  onSubmit: (feedback: FeedbackSubmission) => void
  /** Opens with the reason form showing, for a screen that draws that state. */
  defaultOpen?: boolean
  /** The reason box's starting text, for the same. */
  defaultReason?: string
  className?: string
}

/**
 * `status` is the caller's, and comes straight from the feedback request: `idle` (nothing sent),
 * `sending`, `sent` (also the state of a turn the server says already has feedback), or `error`.
 * An error carries the API's own text, shown as is, so the type refuses an error without one.
 * Whether the reason form is open, and what is typed in it, is the component's own.
 */
type FeedbackProps = FeedbackBaseProps &
  (
    | { status: 'idle' | 'sending' | 'sent'; errorMessage?: undefined }
    | { status: 'error'; errorMessage: string }
  )

type FocusTarget = 'box' | 'no' | 'thanks'

/**
 * "Was this right?" with Yes and No (from the design's Conversation frames). Yes sends at once. No
 * opens a form for an optional reason and moves focus into it, Cancel puts focus back on No, and
 * after a send focus moves to the thank-you line, which is a status. A turn that already has
 * feedback shows the thank-you without moving focus.
 *
 * A reason over 500 characters (counted trimmed, as the API does) can't be sent, and nothing is
 * cut off silently: the count says how far over it is. A failed send keeps what was typed.
 *
 * It renders its pieces as siblings, for `AnswerFooter`'s grid: the question on the left of the
 * first row, and the reason form or an error on a row of its own.
 */
function Feedback(props: FeedbackProps) {
  const { status, onSubmit, defaultOpen = false, defaultReason = '', className } = props
  const [open, setOpen] = useState(defaultOpen)
  const [reason, setReason] = useState(defaultReason)
  // Which send is the latest, so an error is shown where it belongs: in the form if it was the
  // reason that failed, and outside it if it was Yes. A form that starts open is the reason's.
  const [lastSend, setLastSend] = useState<'yes' | 'reason'>('reason')
  const labelId = useId()
  const boxId = useId()
  const countId = useId()
  const noRef = useRef<HTMLButtonElement>(null)
  const boxRef = useRef<HTMLTextAreaElement>(null)
  const thanksRef = useRef<HTMLOutputElement>(null)
  const pendingFocus = useRef<FocusTarget | null>(null)
  const lastStatus = useRef(status)

  const sending = status === 'sending'
  const sent = status === 'sent'
  const length = characterCount(reason)
  const tooLong = length > REASON_LIMIT_CHARACTERS

  // Focus moves after the render that shows its target, so it is set here and not in the handler.
  // A target that can no longer apply is dropped: a send that fails (the status turns to error from
  // something else), or goes back to idle, must not pull focus to the thank-you if "sent" turns up
  // later. An error that was already showing before Yes was pressed is not that send's failure.
  useEffect(() => {
    const before = lastStatus.current
    lastStatus.current = status
    const target = pendingFocus.current
    if (
      target === 'thanks' &&
      ((status === 'error' && before !== 'error') || (status === 'idle' && before === 'sending'))
    ) {
      pendingFocus.current = null
      return
    }
    if (target === 'box' && open) boxRef.current?.focus()
    else if (target === 'no' && !open) noRef.current?.focus()
    else if (target === 'thanks' && status === 'sent') thanksRef.current?.focus()
    else return
    pendingFocus.current = null
  })

  function sendYes() {
    if (sending) return
    pendingFocus.current = 'thanks'
    setLastSend('yes')
    onSubmit({ helpful: true })
  }

  function openForm() {
    if (sending) return
    if (open) {
      // Already open: nothing will re-render, so a pending target would wait for a later render.
      boxRef.current?.focus()
      return
    }
    pendingFocus.current = 'box'
    setOpen(true)
  }

  function cancel() {
    pendingFocus.current = 'no'
    setReason('')
    setOpen(false)
  }

  function sendReason(event: FormEvent) {
    event.preventDefault()
    if (sending) return
    if (tooLong) {
      boxRef.current?.focus()
      return
    }
    const trimmed = trimLikePython(reason)
    pendingFocus.current = 'thanks'
    setLastSend('reason')
    onSubmit(trimmed === '' ? { helpful: false } : { helpful: false, reason: trimmed })
  }

  return (
    <>
      {sent ? (
        <output
          ref={thanksRef}
          tabIndex={-1}
          data-slot="feedback-thanks"
          className={cn('flex items-center gap-2 text-small text-ink', className)}
        >
          <CircleCheck aria-hidden="true" className="size-4 shrink-0 text-success" />
          {conversationCopy.feedbackThanks}
        </output>
      ) : (
        <div
          data-slot="feedback"
          // A fieldset's legend would be in the flex row's way, so this is a labeled group.
          // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role
          role="group"
          aria-labelledby={labelId}
          className={cn('flex items-center gap-2.5', className)}
        >
          <span id={labelId} className="text-small text-ink-muted">
            {conversationCopy.feedbackQuestion}
          </span>
          <div className="flex gap-1.5">
            <Button
              variant="secondary"
              size="sm"
              aria-busy={sending || undefined}
              onClick={sendYes}
            >
              {conversationCopy.yes}
            </Button>
            <Button
              ref={noRef}
              variant="secondary"
              size="sm"
              aria-pressed={open}
              aria-busy={sending || undefined}
              onClick={openForm}
              className="aria-pressed:border-primary aria-pressed:bg-primary-tint"
            >
              {conversationCopy.no}
            </Button>
          </div>
        </div>
      )}
      {!sent && !(open && lastSend === 'reason') && props.status === 'error' && (
        <InlineError message={props.errorMessage} className="col-span-full mt-0 px-0" />
      )}
      {!sent && open && (
        <form
          data-slot="feedback-form"
          onSubmit={sendReason}
          className="col-span-full m-0 flex flex-col gap-2 rounded-lg border border-border p-4"
        >
          <label htmlFor={boxId} className="text-ui font-semibold text-ink">
            {conversationCopy.reasonLabel}{' '}
            <span className="font-regular text-ink-muted">{conversationCopy.optional}</span>
          </label>
          <Textarea
            ref={boxRef}
            id={boxId}
            rows={3}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            aria-describedby={countId}
            aria-invalid={tooLong || undefined}
            placeholder={conversationCopy.reasonPlaceholder}
            className="min-h-0 px-3 py-2.5 text-body"
          />
          {lastSend === 'reason' && props.status === 'error' && (
            <InlineError message={props.errorMessage} className="mt-0 px-0" />
          )}
          {/* Below sm the count has a row of its own above the buttons, which sit at the end. */}
          <div className="flex flex-wrap items-center gap-2">
            <span
              id={countId}
              className={cn(
                'text-small tabular-nums max-sm:basis-full sm:flex-1',
                tooLong ? 'text-danger' : 'text-ink-muted',
              )}
            >
              {conversationCopy.reasonCount(length)}
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={cancel}
              disabled={sending}
              className="text-ink enabled:hover:bg-neutral-hover enabled:hover:text-ink max-sm:ml-auto"
            >
              {conversationCopy.cancel}
            </Button>
            <Button
              type="submit"
              size="sm"
              aria-disabled={tooLong || undefined}
              loading={sending}
              className="px-3.5"
            >
              {conversationCopy.sendFeedback}
            </Button>
          </div>
        </form>
      )}
    </>
  )
}

type AnswerFooterProps = {
  /** `Feedback`. Left out under an escalation panel, which has no "Was this right?". */
  feedback?: ReactNode
  /** `WorkTrace`. */
  work: ReactNode
  className?: string
}

/**
 * The row under a finished answer: "Was this right?" on the left and "Show your work" on the
 * right, as the design draws it at desktop width, and on two rows below 640 px (the design's
 * narrow rule). The reason form and the opened work panel take a full row under them, in the
 * order a person tabs through them. `Feedback` and `WorkTrace` are fragments, so their pieces
 * are this grid's cells.
 */
function AnswerFooter({ feedback, work, className }: AnswerFooterProps) {
  return (
    <div
      data-slot="answer-footer"
      className={cn(
        'grid grid-cols-1 items-center gap-x-3 gap-y-2 sm:grid-cols-[minmax(0,1fr)_auto]',
        className,
      )}
    >
      {feedback}
      {work}
    </div>
  )
}

export { AnswerFooter, Feedback }
export type { AnswerFooterProps, FeedbackProps, FeedbackSubmission }
