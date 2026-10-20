import { cn } from '@/lib/utils'
import { conversationCopy } from './labels'

type UserMessageProps = {
  text: string
  className?: string
}

/**
 * The person's own question: right-aligned on surface-hover, at most 85% of the thread's width
 * (520 px once there is room). It is text only, never Markdown or HTML, with the line breaks and
 * spaces as typed. A hidden "You asked:" leads it, so a screen reader hears who is speaking.
 */
function UserMessage({ text, className }: UserMessageProps) {
  return (
    <div
      data-slot="user-message"
      className={cn(
        'max-w-[85%] self-end rounded-lg bg-surface-hover px-4 py-2.5 text-body text-pretty break-words whitespace-pre-wrap text-ink sm:max-w-[520px]',
        className,
      )}
    >
      <span className="sr-only">{conversationCopy.youAsked}</span>
      {text}
    </div>
  )
}

export { UserMessage }
export type { UserMessageProps }
