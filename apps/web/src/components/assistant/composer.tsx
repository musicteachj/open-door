import { ArrowRight, CircleAlert, Info, Square, TriangleAlert } from 'lucide-react'
import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from 'react'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { AI_DISCLOSURE } from '@/lib/disclosure'
import { cn } from '@/lib/utils'
import { APP_LINK } from './link-class'
import { QUESTION_LIMIT_CHARACTERS, conversationCopy, lengthHint } from './labels'
import { characterCount, trimLikePython } from './text-count'

/** The length hint shows from this many characters (the trimmed text, in code points). */
const LENGTH_HINT_FROM_CHARACTERS = 1800

type ComposerProps = {
  value: string
  onChange: (value: string) => void
  /** Called with the text when the person sends a non-empty question and the composer is not busy. */
  onSubmit: (value: string) => void
  /** A question is being sent. Ask shows a spinner and swallows clicks, and Enter sends nothing. */
  busy?: boolean
  placeholder?: string
  /** An answer is streaming. Stop takes Ask's place, and Enter sends nothing. */
  streaming?: boolean
  /** Stop was pressed. Focus goes back to the box. */
  onStop?: () => void
  /** Enter was pressed with a question typed while an answer streams, for the caller's send error. */
  onSubmitWhileStreaming?: () => void
  /** Why the last send failed, shown under the box (`role="alert"`). The draft is kept, so Ask is the retry. Never worded here. */
  sendError?: string
  /** The assistant is out of budget. The box and Ask are disabled, and the placeholder says why. */
  disabledReason?: 'sandbox' | 'daily'
  /** The personal-data check's text. While it is set, nothing sends. */
  warning?: string
  /** Shows the long-conversation notice above the box. */
  longConversation?: boolean
  /** The notice's "Start a new conversation" button. */
  onNewConversation?: () => void
  /**
   * `docked` is the conversation's: one line that grows with its text up to about four lines, then
   * scrolls. The default is the assistant home's three-row box.
   */
  variant?: 'default' | 'docked'
  className?: string
}

/** Browsers that size a textarea to its text by themselves (`field-sizing: content`). */
const supportsFieldSizing = () =>
  typeof CSS !== 'undefined' &&
  typeof CSS.supports === 'function' &&
  CSS.supports('field-sizing', 'content')

/**
 * The line under the box, and the one thing that goes there, in order:
 * 1. the budget stop's pointer to the Handbook and the Directory. The banner above already says
 *    why nothing can be sent, and these links must always be on the page (focus is handed to one)
 * 2. a question over the limit, because it is why Ask does nothing, and a send error left over
 *    from an earlier try must not hide it
 * 3. the personal-data warning, which blocks sending too
 * 4. a send error from the API
 * 5. the length hint
 * The count is plain text: a status here would be read out on every key. `LengthAnnouncement`
 * speaks it at the points that matter.
 */
function underLine(
  props: Pick<ComposerProps, 'sendError' | 'warning' | 'disabledReason'>,
  count: number | null,
  id: string,
): ReactNode {
  const base = 'm-0 flex items-center gap-2 px-1'
  if (props.disabledReason) {
    const [before, handbook, between, directory, after] = conversationCopy.stillUseParts
    return (
      <p data-slot="composer-line" id={id} className={cn(base, 'text-small text-ink-muted')}>
        <span>
          {before}
          <Link to="/handbook" data-slot="composer-handbook-link" className={APP_LINK}>
            {handbook}
          </Link>
          {between}
          <Link to="/directory" className={APP_LINK}>
            {directory}
          </Link>
          {after}
        </span>
      </p>
    )
  }
  if (count !== null && count > QUESTION_LIMIT_CHARACTERS) {
    return (
      <p
        data-slot="composer-line"
        id={id}
        className={cn(base, 'text-small text-danger tabular-nums')}
      >
        <CircleAlert aria-hidden="true" className="size-4 shrink-0" />
        {conversationCopy.overLimit(count)}
      </p>
    )
  }
  if (props.warning) {
    return (
      <p data-slot="composer-line" id={id} role="alert" className={cn(base, 'text-ui text-ink')}>
        <TriangleAlert aria-hidden="true" className="size-4 shrink-0 text-warning" />
        {props.warning}
      </p>
    )
  }
  if (props.sendError) {
    return (
      <p data-slot="composer-line" id={id} role="alert" className={cn(base, 'text-ui text-danger')}>
        <CircleAlert aria-hidden="true" className="size-4 shrink-0" />
        {props.sendError}
      </p>
    )
  }
  if (count !== null) {
    return (
      <p
        data-slot="composer-line"
        id={id}
        className={cn(base, 'text-small text-ink-muted tabular-nums')}
      >
        {lengthHint(count)}
      </p>
    )
  }
  return null
}

/**
 * A hidden polite status, always in the page so a screen reader is already watching it. It says
 * the count when the draft first reaches 1,800 characters, says so when it goes over 2,000 and
 * when it comes back under, and nothing in between, so typing is never read out key by key. A
 * draft that is long when the page loads is not announced.
 */
function LengthAnnouncement({ count }: { count: number | null }) {
  const phase = count === null ? 'short' : count > QUESTION_LIMIT_CHARACTERS ? 'over' : 'near'
  const [spoken, setSpoken] = useState('')
  const [lastPhase, setLastPhase] = useState(phase)
  // Adjusted while rendering, not in an effect: the region is already in the page, so the text
  // changes in an element a screen reader is watching, and there is no second render to wait for.
  if (phase !== lastPhase) {
    setLastPhase(phase)
    if (phase === 'short') setSpoken('')
    else if (phase === 'over') setSpoken(conversationCopy.overLimit(count ?? 0))
    else if (lastPhase === 'over') setSpoken(conversationCopy.underLimitAgain)
    else setSpoken(lengthHint(count ?? 0))
  }
  return (
    <output data-slot="length-announcement" className="sr-only">
      {spoken}
    </output>
  )
}

/**
 * The assistant's ask box, from Composer.jsx and the design's Conversation frames. Enter sends,
 * Shift+Enter adds a line, and an Enter that confirms an IME composition (Japanese, Chinese,
 * Korean) is not a send. Ask on an empty box moves focus into the box instead. The AI disclosure
 * is always shown, and describes the box. Controlled: the chat store owns the draft, so a "Try
 * asking" row can fill it.
 *
 * In a conversation it has more states. While an answer streams, Stop takes Ask's place and Enter
 * is handed to the caller. A budget stop disables the box and Ask. The length is counted the way
 * the API counts it (the trimmed text, in code points): from 1,800 characters a hint shows, and
 * past 2,000 the question can't be sent. There is no `maxLength`, which would cut a paste without
 * saying so. The personal-data warning blocks sending too. Only one line shows under the box, by
 * the order in `underLine`.
 */
function Composer({
  value,
  onChange,
  onSubmit,
  busy = false,
  placeholder = 'Ask about time off, pay, benefits, or policy…',
  streaming = false,
  onStop,
  onSubmitWhileStreaming,
  sendError,
  disabledReason,
  warning,
  longConversation = false,
  onNewConversation,
  variant = 'default',
  className,
}: ComposerProps) {
  const boxRef = useRef<HTMLTextAreaElement>(null)
  const formRef = useRef<HTMLFormElement>(null)
  // Where focus last was inside the form, so a change that removes or disables that control can
  // hand focus on. The control is gone by the time an effect runs, so it is noted as it happens.
  const focusInside = useRef<'stop' | 'ask' | 'other' | null>(null)
  const wasStreaming = useRef(streaming)
  const hadBudgetStop = useRef(disabledReason !== undefined)
  const disclosureId = useId()
  const lineId = useId()
  const docked = variant === 'docked'

  // Firefox and Safari have no `field-sizing`, so a docked box sizes itself to its text there. The
  // CSS maximum height stops the growth, and the box scrolls past it.
  useLayoutEffect(() => {
    const box = boxRef.current
    if (!box) return
    if (!docked || supportsFieldSizing()) {
      // Not ours to size: leave nothing behind from when it was docked.
      box.style.height = ''
      return
    }
    box.style.height = 'auto'
    if (box.scrollHeight > 0) box.style.height = `${box.scrollHeight}px`
  }, [docked, value])

  // Notes where focus is inside the form as it moves (a form has no focus handlers of its own to
  // set, so these are listeners).
  useEffect(() => {
    const form = formRef.current
    if (!form) return
    const onFocusIn = (event: FocusEvent) => {
      const target = event.target
      const slot = target instanceof HTMLElement ? target.dataset.slot : undefined
      focusInside.current =
        slot === 'composer-stop' ? 'stop' : slot === 'composer-ask' ? 'ask' : 'other'
    }
    // Moving to something outside the form means focus is not in the composer any more.
    const onFocusOut = (event: FocusEvent) => {
      const next = event.relatedTarget
      if (next instanceof Node) {
        if (!form.contains(next)) focusInside.current = null
        return
      }
      // Focus went to nothing: the person clicked plain text or left the window, or the browser is
      // reporting the removal of the focused node (Stop, when an answer ends). A moment later the
      // node tells which: one still in the page means focus really left, and one that is gone is
      // the composer's own doing, which the effect below hands on.
      const left = event.target
      queueMicrotask(() => {
        if (left instanceof Node && left.isConnected) focusInside.current = null
      })
    }
    form.addEventListener('focusin', onFocusIn)
    form.addEventListener('focusout', onFocusOut)
    return () => {
      form.removeEventListener('focusin', onFocusIn)
      form.removeEventListener('focusout', onFocusOut)
    }
  }, [])

  // Focus would drop to the page when the control under it goes away or is disabled. A starting
  // answer takes Ask away (Stop takes its place), a finished one takes Stop away, and a budget
  // stop disables the box and Ask. Handed on only if focus really was lost, and was in the
  // composer: Ask's focus goes to Stop, Stop's to the box, and the box's to the Handbook link.
  useLayoutEffect(() => {
    const answerEnded = wasStreaming.current && !streaming
    const answerStarted = !wasStreaming.current && streaming
    const budgetStopped = !hadBudgetStop.current && disabledReason !== undefined
    wasStreaming.current = streaming
    hadBudgetStop.current = disabledReason !== undefined
    const active = document.activeElement
    const box = boxRef.current
    // A disabled control may still be the active element in some browsers, and is as good as lost.
    const lost =
      !active ||
      active === document.body ||
      ((active === box || active instanceof HTMLButtonElement) &&
        (active as HTMLElement & { disabled: boolean }).disabled)
    if (!lost || focusInside.current === null) return
    if (budgetStopped) {
      formRef.current?.querySelector<HTMLElement>('[data-slot="composer-handbook-link"]')?.focus()
    } else if (answerEnded && focusInside.current === 'stop') {
      box?.focus()
    } else if (answerStarted && focusInside.current === 'ask') {
      formRef.current?.querySelector<HTMLElement>('[data-slot="composer-stop"]')?.focus()
    }
  }, [streaming, disabledReason])

  // The hint follows the count it shows, in code points: 1,000 emoji are 2,000 UTF-16 units and
  // 1,000 characters. Only that count is compared with the limits, never the string's length.
  const characters = characterCount(value)
  const count = characters >= LENGTH_HINT_FROM_CHARACTERS ? characters : null
  const tooLong = count !== null && count > QUESTION_LIMIT_CHARACTERS
  const blocked = tooLong || Boolean(warning)
  const line = underLine({ sendError, warning, disabledReason }, count, lineId)
  const disabled = disabledReason !== undefined
  const boxPlaceholder =
    disabledReason === 'sandbox'
      ? conversationCopy.sandboxDisabledPlaceholder
      : disabledReason === 'daily'
        ? conversationCopy.dailyDisabledPlaceholder
        : placeholder

  function send() {
    if (disabled) return
    if (streaming) {
      if (trimLikePython(value) !== '') onSubmitWhileStreaming?.()
      return
    }
    if (busy) return
    if (blocked || trimLikePython(value) === '') {
      boxRef.current?.focus()
      return
    }
    onSubmit(value)
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    send()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey) return
    // keyCode 229 is how older engines report a key pressed during composition.
    if (event.nativeEvent.isComposing || event.keyCode === 229) return
    event.preventDefault()
    send()
  }

  function stop() {
    onStop?.()
    boxRef.current?.focus()
  }

  return (
    <form
      data-slot="composer"
      onSubmit={handleSubmit}
      ref={formRef}
      className={cn('m-0 flex w-full max-w-content flex-col gap-2.5', className)}
    >
      {longConversation && (
        <output
          data-slot="composer-notice"
          className="flex items-center gap-3 rounded-md border border-border bg-surface-sunken py-2 pr-2 pl-4 max-sm:flex-wrap"
        >
          <Info aria-hidden="true" className="size-4 shrink-0 text-ink-muted" />
          <span className="min-w-48 flex-1 text-ui text-pretty text-ink">
            {conversationCopy.longConversation}
          </span>
          {onNewConversation && (
            <Button variant="secondary" size="sm" onClick={onNewConversation} className="shrink-0">
              {conversationCopy.startNewConversation}
            </Button>
          )}
        </output>
      )}
      <div
        className={cn(
          'rounded-lg border border-input-border bg-surface-raised shadow-xs transition-[border-color,box-shadow] focus-within:border-primary focus-within:shadow-focus-halo hover:border-input-border-hover focus-within:hover:border-primary',
          disabled && 'border-border bg-surface-sunken shadow-none hover:border-border',
        )}
      >
        <Textarea
          ref={boxRef}
          aria-label="Ask Open Door"
          aria-describedby={line ? `${disclosureId} ${lineId}` : disclosureId}
          aria-invalid={tooLong || undefined}
          rows={docked ? 1 : 3}
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={boxPlaceholder}
          className={cn(
            'min-h-0 resize-none rounded-none border-0 bg-transparent px-6 pt-5 pb-2 text-body-lg shadow-none hover:border-0 focus:border-0 focus:shadow-none disabled:border-0 disabled:bg-transparent disabled:placeholder:text-disabled-fg',
            // Four lines of 28 px and the box's padding, then it scrolls.
            docked && 'field-sizing-content max-h-35 overflow-y-auto',
          )}
        />
        <div className="flex flex-wrap items-center gap-4 border-t border-border-subtle py-3 pr-3 pl-4 sm:flex-nowrap sm:pl-6">
          <p
            id={disclosureId}
            className={cn(
              'm-0 flex items-center gap-2 text-small text-ink-muted',
              // The conversation's footer wraps below sm (notes.md, screen 07): the disclosure
              // takes its own row above the button. The home composer keeps them side by side.
              docked ? 'max-sm:basis-full sm:flex-1' : 'flex-1',
            )}
          >
            <Info aria-hidden="true" className="size-3.5 shrink-0" />
            {AI_DISCLOSURE}
          </p>
          {/* Keyed apart: if one node served as both, Stop's click could end the stream and turn
              the node into a submit button before the click is over, and submit the draft. */}
          {streaming ? (
            <Button
              key="stop"
              data-slot="composer-stop"
              type="button"
              variant="secondary"
              onClick={stop}
              className={cn('pr-4 pl-3.5', docked && 'max-sm:ml-auto')}
            >
              <Square aria-hidden="true" className="size-3.5 fill-current" />
              {conversationCopy.stop}
            </Button>
          ) : (
            <Button
              key="ask"
              data-slot="composer-ask"
              type="submit"
              loading={busy}
              disabled={disabled}
              aria-disabled={blocked || undefined}
              className={cn('pr-3.5', docked && 'max-sm:ml-auto')}
            >
              Ask
              <ArrowRight aria-hidden="true" className="size-4" />
            </Button>
          )}
        </div>
      </div>
      <LengthAnnouncement count={disabled ? null : count} />
      {line}
    </form>
  )
}

export { Composer }
export type { ComposerProps }
