import { ArrowRight, BookOpen, X } from 'lucide-react'
import { useEffect, useRef, type ComponentProps, type ElementType } from 'react'
import { Link } from 'react-router'
import type { PassageView } from '@/api/generated'
import { InlineError } from '@/components/feedback/inline-error'
import { Skeleton } from '@/components/ui/skeleton'
import { buttonVariants } from '@/components/ui/button-variants'
import { cn } from '@/lib/utils'
import { ApplicabilityBadge } from './applicability-badge'
import { AppliesMarker } from './applies-marker'
import { CitedPassage } from './cited-passage'
import { PassageText } from './handbook-blocks'
import { handbookCopy, handbookPath, panelEyebrow } from './labels'
import { LastUpdated } from './last-updated'

type PassagePanelProps = {
  state: 'open' | 'loading' | 'error'
  /** The section and passage being shown; they build the "Open in handbook" link in every state. */
  sectionId: string
  passageId: string
  /** What the passage route returned. Needed when `state` is "open". */
  view?: PassageView
  /** The section's group ("California addendum"), for the eyebrow while there's no `view` yet. */
  groupName?: string
  onClose: () => void
  /** Shows the error state's Retry button. */
  onRetry?: () => void
  /**
   * The element for the title, an `h2` by default. A dialog passes its own title component, so the
   * visible title is what names the dialog. While there is no passage to title (loading, or an
   * error) it still renders one, hidden, with the eyebrow's words, so the name never goes missing.
   */
  titleAs?: ElementType
  /**
   * Whether the panel is a labeled landmark ("Handbook passage"). A dialog sets false: the dialog
   * is the landmark, and a second name inside it would be read twice.
   */
  landmark?: boolean
  className?: string
}

/**
 * Shows one cited passage beside the content (PassagePanel.jsx), shared by the handbook and the
 * assistant's source panel. The header and footer stay put and the body scrolls inside the panel.
 * The sketch takes the strings `before`, `cited`, and `after`; this takes the API's `PassageView`
 * and renders each neighbor with its own markup, a list included. The data comes in as props: the
 * host fetches it. The sketch's `href` and `onOpen` become a router `Link` built from the ids.
 *
 * It isn't modal, so this is not a Radix Dialog and nothing traps focus. When it shows a passage,
 * focus moves to the title. Escape and the close button call `onClose`; the host puts focus back
 * on the citation that opened it, since only the host knows which that was.
 */
function PassagePanel({
  state,
  sectionId,
  passageId,
  view,
  groupName,
  onClose,
  onRetry,
  titleAs,
  landmark = true,
  className,
}: PassagePanelProps) {
  const Title: ElementType = titleAs ?? 'h2'
  const Root = (landmark ? 'aside' : 'div') as ElementType<ComponentProps<'aside'>>
  const titleRef = useRef<HTMLHeadingElement>(null)
  const panelRef = useRef<HTMLElement>(null)
  const hasView = state === 'open' && view !== undefined

  // Focus the title when a passage first shows, and again when the host swaps in another one, so
  // a screen reader hears the new passage.
  useEffect(() => {
    if (hasView) titleRef.current?.focus()
  }, [hasView, sectionId, passageId])

  // Escape closes the panel when focus is inside it or on the page body. It never closes it from
  // a field elsewhere (a half-typed message), during an IME composition, or when something else
  // (an open menu, say) already used the key.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented || event.isComposing) return
      const target = event.target
      const inside = target instanceof Node && panelRef.current?.contains(target)
      if (inside || target === document.body) onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  // Without the section, an ID that starts with a state code ("CA-4.3") is an addendum.
  const number = /^[A-Z]{2}-/.test(sectionId) ? sectionId : `§${sectionId}`
  const eyebrow = view
    ? panelEyebrow(view.section)
    : groupName === undefined
      ? `Handbook ${sectionId}`
      : `Handbook ${number} · ${groupName}`
  const contextClass = 'mb-4 text-body text-ink-muted'

  return (
    <Root
      ref={panelRef}
      aria-label={landmark ? 'Handbook passage' : undefined}
      aria-busy={state === 'loading'}
      className={cn('flex h-full min-h-0 flex-col bg-surface-raised text-ink', className)}
    >
      <header className="flex flex-none flex-col gap-1.5 border-b border-border-subtle py-3.5 pr-3.5 pb-[18px] pl-6">
        <div className="flex items-center justify-between gap-3">
          <span className="inline-flex min-w-0 items-center gap-2 text-small text-ink-muted">
            <BookOpen aria-hidden="true" className="size-3.5 shrink-0" />
            {eyebrow}
          </span>
          <button
            type="button"
            aria-label={handbookCopy.closePassage}
            onClick={onClose}
            className="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-sm text-ink-muted transition-colors hover:bg-neutral-hover hover:text-ink"
          >
            <X aria-hidden="true" className="size-4" />
          </button>
        </div>
        {hasView && (
          <>
            <Title ref={titleRef} tabIndex={-1} className="m-0 text-h2 font-semibold outline-none">
              {view.section.title}
            </Title>
            <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-2">
              <ApplicabilityBadge label={view.section.audienceLabel} />
              <AppliesMarker applies={view.section.appliesToMe} />
              <LastUpdated date={view.section.lastUpdated} />
            </div>
          </>
        )}
        {!hasView && titleAs !== undefined && <Title className="sr-only">{eyebrow}</Title>}
        {state === 'loading' && (
          <>
            <Skeleton className="my-1 h-5 w-40" />
            <Skeleton className="mt-2 w-64" />
          </>
        )}
      </header>

      <div
        // A scrolling region has to take focus so the keyboard can scroll it.
        // oxlint-disable-next-line jsx-a11y/no-noninteractive-tabindex
        tabIndex={0}
        aria-label="Passage text"
        className="min-h-0 flex-1 overflow-auto px-6 pt-5 pb-6 focus-visible:shadow-[inset_0_0_0_2px_var(--color-focus-ring)] focus-visible:outline-none"
      >
        {hasView && (
          <>
            {view.previous && <PassageText passage={view.previous} className={contextClass} />}
            <CitedPassage compact>
              <PassageText passage={view.passage} />
            </CitedPassage>
            {view.next && <PassageText passage={view.next} className={cn(contextClass, 'mb-0')} />}
          </>
        )}
        {state === 'loading' && (
          <div className="flex flex-col gap-3">
            <Skeleton className="w-full" />
            <Skeleton className="w-[92%]" />
            <Skeleton className="w-[64%]" />
            <Skeleton className="mt-3 h-24 w-full rounded-lg" />
            <Skeleton className="mt-3 w-[88%]" />
            <Skeleton className="w-[72%]" />
            <span className="sr-only">{handbookCopy.loading.passage}</span>
          </div>
        )}
        {state === 'error' && (
          <InlineError message={handbookCopy.passageError} onRetry={onRetry} className="mt-0 p-0" />
        )}
      </div>

      <footer className="flex flex-none border-t border-border-subtle px-6 py-3">
        <Link
          to={handbookPath(sectionId, passageId)}
          className={cn(buttonVariants({ variant: 'secondary' }), 'no-underline hover:text-ink')}
        >
          {handbookCopy.openInHandbook}
          <ArrowRight aria-hidden="true" className="size-4" strokeWidth={2} />
        </Link>
      </footer>
    </Root>
  )
}

export { PassagePanel }
export type { PassagePanelProps }
