import { ArrowRight } from 'lucide-react'
import { useId } from 'react'
import { cn } from '@/lib/utils'

type TryAskingListProps = {
  /** The questions to suggest. Renders nothing when there are none. */
  items: readonly string[]
  /** A row was chosen. The page puts the question in the composer; nothing is sent. */
  onPick: (question: string) => void
  label?: string
  className?: string
}

/**
 * Suggested questions, from TryAskingList.jsx and TryAskingRow.jsx: a labeled region holding a
 * list of buttons in two columns (one on a narrow screen). Choosing one only calls `onPick`, so
 * the person can edit the question before sending it.
 */
function TryAskingList({ items, onPick, label = 'Try asking', className }: TryAskingListProps) {
  const labelId = useId()
  if (items.length === 0) return null
  return (
    <section
      data-slot="try-asking-list"
      aria-labelledby={labelId}
      className={cn('flex w-full max-w-content flex-col gap-2', className)}
    >
      <h2 id={labelId} className="m-0 text-small font-regular text-ink-muted">
        {label}
      </h2>
      <ul className="m-0 grid list-none grid-cols-1 gap-x-8 p-0 sm:grid-cols-2">
        {items.map((question) => (
          <li key={question} className="flex">
            <button
              type="button"
              data-slot="try-asking-row"
              onClick={() => onPick(question)}
              className="flex min-h-row w-full cursor-pointer items-center justify-between gap-3 rounded-none border-0 border-b border-border-subtle bg-transparent px-3 text-left text-body text-ink transition-colors hover:bg-primary-tint focus-visible:relative focus-visible:z-10"
            >
              <span>{question}</span>
              <ArrowRight aria-hidden="true" className="size-4 shrink-0" />
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export { TryAskingList }
export type { TryAskingListProps }
