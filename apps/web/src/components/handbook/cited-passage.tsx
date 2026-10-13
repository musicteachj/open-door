import { Quote, X } from 'lucide-react'
import { useId, type ComponentProps, type ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { handbookCopy } from './labels'

type CitedPassageProps = Omit<
  ComponentProps<'section'>,
  'children' | 'role' | 'aria-labelledby'
> & {
  /** The passage's own elements (a paragraph or a list). */
  children: ReactNode
  /** Shows "Clear highlight" (the section page only). */
  onClear?: () => void
  /** The 15 px version for the passage panel. */
  compact?: boolean
}

/**
 * The highlighted passage a citation points to (CitedPassage.jsx): a region labeled "Cited
 * passage", so a screen reader hears the label first, with a quote icon and a slim cinnamon bar.
 * The bar is decoration; the label and icon carry the meaning. The region takes focus by script
 * (`tabIndex=-1`), which the host uses for a deep link. The sketch's `autoFocus` is the host's job
 * here (HandbookBlocks scrolls and focuses it), so a panel can show one without stealing focus.
 * The sketch wraps the text in a `p`; this takes children so a list can be cited too.
 */
function CitedPassage({
  children,
  onClear,
  compact = false,
  className,
  ...props
}: CitedPassageProps) {
  const labelId = useId()
  return (
    <section
      aria-labelledby={labelId}
      tabIndex={-1}
      data-compact={compact}
      {...props}
      className={cn(
        'relative rounded-md bg-primary-tint outline-none before:absolute before:top-2 before:bottom-2 before:left-0 before:w-[3px] before:rounded-xs before:bg-marker',
        compact
          ? '-mx-3 mb-4 px-3 pt-2.5 pb-3.5 text-body'
          : '-mx-5 px-5 pt-2.5 pb-[18px] text-body-lg max-[760px]:-mx-3 max-[760px]:px-3',
        className,
      )}
    >
      <div className="mb-1 flex items-center justify-between gap-3">
        <span
          id={labelId}
          className="inline-flex items-center gap-2 text-small font-semibold text-ink"
        >
          <Quote aria-hidden="true" className="size-4 text-primary" />
          {handbookCopy.citedPassage}
        </span>
        {onClear && (
          <button
            type="button"
            onClick={onClear}
            className="-mr-2 inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-sm border-0 bg-transparent px-2 text-small font-semibold text-ink hover:bg-surface-raised"
          >
            <X aria-hidden="true" className="size-3.5" />
            {handbookCopy.clearHighlight}
          </button>
        )}
      </div>
      <div className="text-ink [&_ol]:m-0 [&_p]:m-0 [&_ul]:m-0">{children}</div>
    </section>
  )
}

export { CitedPassage }
export type { CitedPassageProps }
