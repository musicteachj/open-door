import { Check, LoaderCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

type StatusStep = {
  id: string
  /** The step's words, from the API (a `status` event or a tool's start): "Searching the handbook…". */
  text: string
  /** A finished step shows a check, and the current one a spinner. */
  done: boolean
}

type StatusLineProps = {
  steps: StatusStep[]
  className?: string
}

/**
 * What the assistant is doing before and between its words (from the design's Conversation
 * frames): finished steps with a check, in muted ink, and the current step with a spinner. It is a
 * polite live region that is not atomic (a `status` role is atomic by default, which would read
 * the whole list again on each change), so a screen reader hears the step that was added or
 * changed. The spinner stops under
 * prefers-reduced-motion (base.css turns every animation off). With no steps it is an empty region
 * that takes no room, because a live region inserted along with its first text is often not
 * announced: the message shows it while it streams, so it is in the page before the first step.
 */
function StatusLine({ steps, className }: StatusLineProps) {
  return (
    <div
      data-slot="status-line"
      // A div, not an output: an output holds phrasing content only, and this holds a list.
      // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role
      role="status"
      aria-live="polite"
      aria-atomic="false"
      // Empty, it takes no room (the negative margin cancels the message's gap above it).
      className={cn('empty:-mt-3.5', className)}
    >
      {steps.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
          {steps.map((step) => (
            <li
              key={step.id}
              className={cn(
                'flex items-center gap-2 text-ui',
                step.done ? 'text-ink-muted' : 'text-ink',
              )}
            >
              {step.done ? (
                <Check data-slot="status-check" aria-hidden="true" className="size-4 shrink-0" />
              ) : (
                <LoaderCircle
                  data-slot="status-spinner"
                  aria-hidden="true"
                  className="size-4 shrink-0 animate-spin text-primary"
                />
              )}
              {step.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export { StatusLine }
export type { StatusLineProps, StatusStep }
