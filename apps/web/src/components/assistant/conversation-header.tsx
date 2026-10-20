import { SquarePen } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { conversationCopy } from './labels'

/**
 * "Conversations are deleted with your sandbox after 24 hours." The header shows it from 640 px up.
 * Below that the page shows this same line under the composer, so it is its own piece.
 */
function RetentionLine({ className }: { className?: string }) {
  return (
    <p
      data-slot="retention-line"
      className={cn('m-0 text-small text-pretty text-ink-muted', className)}
    >
      {conversationCopy.retention}
    </p>
  )
}

type ConversationHeaderProps = {
  onNewConversation: () => void
  /** The sandbox pill, at the right. The page passes its own, so this stays presentational. */
  children?: ReactNode
  className?: string
}

/**
 * The row above the thread (from the design's Conversation frames): the retention line, "Start a
 * new conversation", and the sandbox pill. Below 640 px the retention line is hidden, the button
 * becomes an icon button next to the pill, and its name stays "Start a new conversation".
 */
function ConversationHeader({ onNewConversation, children, className }: ConversationHeaderProps) {
  return (
    <div data-slot="conversation-header" className={cn('flex items-center gap-4', className)}>
      <RetentionLine className="min-w-0 flex-1 max-sm:hidden" />
      <Button
        variant="ghost"
        size="sm"
        onClick={onNewConversation}
        className="text-ink enabled:hover:bg-neutral-hover enabled:hover:text-ink max-sm:ml-auto max-sm:size-8 max-sm:px-0 sm:gap-2 sm:px-2.5"
      >
        <SquarePen aria-hidden="true" className="size-4" />
        <span className="max-sm:sr-only">{conversationCopy.startNewConversation}</span>
      </Button>
      {children}
    </div>
  )
}

export { ConversationHeader, RetentionLine }
export type { ConversationHeaderProps }
