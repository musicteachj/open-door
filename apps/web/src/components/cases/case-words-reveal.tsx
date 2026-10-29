import { Eye, EyeOff, Lock } from 'lucide-react'
import { useId } from 'react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { detailCopy } from './labels'

type WordsState = 'hidden' | 'loading' | 'shown' | 'failed'

type CaseWordsRevealProps = {
  /** The person's given name, for "Priya's words". */
  firstName: string
  state: WordsState
  /** The words, for `shown`. Plain text: never Markdown, never a link. */
  words?: string
  /** Show the words. The page fetches them (an audited read) and holds them in its own state. */
  onShow?: () => void
  /** Hide them again. Hiding is not recorded. */
  onHide?: () => void
  className?: string
}

/**
 * The person's own words, hidden on every view until HR opens them (CaseWordsReveal.jsx). The
 * button is a disclosure (`aria-expanded`, `aria-controls` on the words' container) and keeps
 * focus. This holds no data of its own: the page passes the words in and decides when they go.
 */
function CaseWordsReveal({
  firstName,
  state,
  words,
  onShow,
  onHide,
  className,
}: CaseWordsRevealProps) {
  const headingId = useId()
  const bodyId = useId()
  const open = state === 'shown'
  return (
    <section
      data-slot="case-words"
      aria-labelledby={headingId}
      className={cn(
        'flex flex-col gap-3.5 rounded-lg border border-confidential-border bg-confidential-tint px-6 pt-5 pb-5.5 max-sm:px-4',
        className,
      )}
    >
      <h2 id={headingId} className="m-0 flex items-center gap-2.5 text-body font-semibold">
        <Lock aria-hidden="true" className="size-4 text-primary" />
        {detailCopy.wordsOf(firstName)}
      </h2>
      {state === 'failed' ? (
        // Mounted fresh when the open fails, so it is announced while focus stays on the button.
        <p role="alert" className="m-0 text-body">
          {detailCopy.wordsFailed(firstName)}
        </p>
      ) : (
        !open && <p className="m-0 text-body">{detailCopy.wordsHidden(firstName)}</p>
      )}
      <div id={bodyId}>
        {open && <p className="m-0 text-[16px]/6.5 text-pretty whitespace-pre-wrap">{words}</p>}
      </div>
      <div>
        {state === 'failed' ? (
          // A retry, not a disclosure: no `aria-expanded` or `aria-controls`.
          <Button variant="secondary" onClick={onShow}>
            {detailCopy.tryAgain}
          </Button>
        ) : (
          <Button
            variant="secondary"
            aria-expanded={open}
            aria-controls={bodyId}
            loading={state === 'loading'}
            onClick={open ? onHide : onShow}
            className="max-sm:w-full"
          >
            {!(state === 'loading') &&
              (open ? (
                <EyeOff aria-hidden="true" className="size-4" />
              ) : (
                <Eye aria-hidden="true" className="size-4" />
              ))}
            {open ? detailCopy.hideWords(firstName) : detailCopy.showWords(firstName)}
          </Button>
        )}
      </div>
    </section>
  )
}

export { CaseWordsReveal }
export type { CaseWordsRevealProps, WordsState }
