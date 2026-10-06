import { ArrowRight, Info } from 'lucide-react'
import { useId, useRef, type FormEvent, type KeyboardEvent } from 'react'
import { InlineError } from '@/components/feedback/inline-error'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { AI_DISCLOSURE } from '@/lib/disclosure'
import { cn } from '@/lib/utils'

type ComposerProps = {
  value: string
  onChange: (value: string) => void
  /** Called with the text when the person sends a non-empty question and the composer is not busy. */
  onSubmit: (value: string) => void
  /** A question is being sent. Ask shows a spinner and swallows clicks, and Enter sends nothing. */
  busy?: boolean
  /** The message for a failed send. Shows an inline error with Retry, which sends `value` again. */
  error?: string
  placeholder?: string
  className?: string
}

/**
 * The assistant's ask box, from Composer.jsx. Enter sends, Shift+Enter adds a line, and an Enter
 * that confirms an IME composition (Japanese, Chinese, Korean) is not a send. Ask on an empty box
 * moves focus into the box instead. The AI disclosure is always shown, and describes the box.
 * Controlled: the chat store owns the draft, so a "Try asking" row can fill it.
 */
function Composer({
  value,
  onChange,
  onSubmit,
  busy = false,
  error,
  placeholder = 'Ask about time off, pay, benefits, or policy…',
  className,
}: ComposerProps) {
  const boxRef = useRef<HTMLTextAreaElement>(null)
  const disclosureId = useId()

  function send() {
    if (busy) return
    if (value.trim() === '') {
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

  return (
    <form
      data-slot="composer"
      onSubmit={handleSubmit}
      className={cn('m-0 w-full max-w-content', className)}
    >
      <div className="rounded-lg border border-input-border bg-surface-raised shadow-xs transition-[border-color,box-shadow] focus-within:border-primary focus-within:shadow-focus-halo hover:border-input-border-hover focus-within:hover:border-primary">
        <Textarea
          ref={boxRef}
          aria-label="Ask Open Door"
          aria-describedby={disclosureId}
          rows={3}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className="min-h-0 resize-none rounded-none border-0 bg-transparent px-6 pt-5 pb-2 text-body-lg shadow-none hover:border-0 focus:border-0 focus:shadow-none"
        />
        <div className="flex flex-wrap items-center gap-4 border-t border-border-subtle py-3 pr-3 pl-4 sm:flex-nowrap sm:pl-6">
          <p
            id={disclosureId}
            className="m-0 flex flex-1 items-center gap-2 text-small text-ink-muted"
          >
            <Info aria-hidden="true" className="size-3.5 shrink-0" />
            {AI_DISCLOSURE}
          </p>
          <Button type="submit" loading={busy} className="pr-3.5">
            Ask
            <ArrowRight aria-hidden="true" className="size-4" />
          </Button>
        </div>
      </div>
      {error !== undefined && <InlineError message={error} onRetry={send} />}
    </form>
  )
}

export { Composer }
export type { ComposerProps }
