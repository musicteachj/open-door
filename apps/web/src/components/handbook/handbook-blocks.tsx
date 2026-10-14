import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import type { Inline, ListPassage, ParagraphPassage, SectionDetail } from '@/api/generated'
import { cn } from '@/lib/utils'
import { CitedPassage } from './cited-passage'
import { handbookPath } from './labels'

type Passage = ParagraphPassage | ListPassage

/** One run of text. The text is a React child, so markup in it is shown, never parsed. */
function InlineRun({ run }: { run: Inline }) {
  let node: ReactNode = run.text
  if (run.bold) node = <strong className="font-semibold">{node}</strong>
  if (run.italic) node = <em>{node}</em>
  if (run.linkSectionId !== null) {
    node = (
      <Link to={handbookPath(run.linkSectionId)} className="text-primary underline">
        {node}
      </Link>
    )
  }
  return node
}

function Inlines({ runs }: { runs: Inline[] }) {
  return runs.map((run, index) => (
    <Fragment key={index}>
      <InlineRun run={run} />
    </Fragment>
  ))
}

type PassageTextProps = {
  passage: Passage
  className?: string
  /** Added to the paragraph or list element, for the passage's id on the page. */
  elementProps?: Record<string, string | number>
}

/** A passage's own element: a paragraph, or a bulleted or numbered list. */
function PassageText({ passage, className, elementProps }: PassageTextProps) {
  if (passage.kind === 'paragraph') {
    return (
      <p className={cn('m-0 text-pretty', className)} {...elementProps}>
        <Inlines runs={passage.inlines} />
      </p>
    )
  }
  const List = passage.ordered ? 'ol' : 'ul'
  return (
    <List
      className={cn('m-0 pl-6', passage.ordered ? 'list-decimal' : 'list-disc', className)}
      {...elementProps}
    >
      {passage.items.map((item, index) => (
        <li key={index}>
          <Inlines runs={item} />
        </li>
      ))}
    </List>
  )
}

type HandbookBlocksProps = {
  blocks: SectionDetail['blocks']
  /** The passage a citation points to; it renders as the "Cited passage" region. */
  citedPassageId?: string
  /** Shows "Clear highlight" on the cited passage. */
  onClearCitation?: () => void
  /** Scroll the cited passage into view and move focus to it (a deep link). */
  focusCited?: boolean
  /** Called after the cited passage has been scrolled to and focused, so a page can do it once. */
  onCitedFocused?: () => void
  className?: string
}

/**
 * A section's body: headings, paragraphs, and lists (the section screenshot; the sketches have no
 * blocks component). Each passage carries `data-passage-id` and an `id` of `passage-<id>`, which
 * the page can scroll to. The cited one is wrapped in `CitedPassage`, which carries those instead.
 * The scroll-and-focus effect runs when this mounts and whenever the blocks or the cited id change,
 * so the page can keep it mounted from one section to the next.
 */
function HandbookBlocks({
  blocks,
  citedPassageId,
  onClearCitation,
  focusCited = false,
  onCitedFocused,
  className,
}: HandbookBlocksProps) {
  const citedRef = useRef<HTMLElement>(null)
  // The latest callback, read inside the effect, so a new function each render never re-runs it.
  const focusedCallback = useRef(onCitedFocused)
  useEffect(() => {
    focusedCallback.current = onCitedFocused
  })
  // `blocks` is a dependency because passage ids restart in every section: following a citation
  // from 4.3's p2 to CA-4.3's p2 changes the blocks but not the id.
  useEffect(() => {
    const el = citedRef.current
    if (focusCited && el) {
      el.scrollIntoView({ block: 'center' })
      el.focus({ preventScroll: true })
      focusedCallback.current?.()
    }
  }, [focusCited, citedPassageId, blocks])

  // "Clear highlight" removes the region, and the button with it. Focus moves to the same passage,
  // now plain, so a keyboard user keeps their place instead of starting from the top of the page.
  // The cleared passage only counts while the same blocks show and nothing new is cited, so it
  // never pulls focus away from a later citation or into another section's passage of that id.
  const [cleared, setCleared] = useState<{ id: string; blocks: SectionDetail['blocks'] } | null>(
    null,
  )
  const refocusId =
    cleared && cleared.blocks === blocks && citedPassageId === undefined ? cleared.id : null
  useEffect(() => {
    if (refocusId) document.getElementById(`passage-${refocusId}`)?.focus({ preventScroll: true })
  }, [refocusId])
  const handleClear =
    onClearCitation &&
    (() => {
      if (citedPassageId) setCleared({ id: citedPassageId, blocks })
      onClearCitation()
    })

  return (
    <div className={cn('flex flex-col gap-4 text-body-lg text-ink', className)}>
      {blocks.map((block, index) => {
        if (block.type === 'heading') {
          return block.level === 2 ? (
            <h2 key={index} className="m-0 mt-4 text-h2 font-semibold">
              {block.text}
            </h2>
          ) : (
            <h3 key={index} className="m-0 mt-2 text-body-lg font-semibold">
              {block.text}
            </h3>
          )
        }
        const ids = {
          id: `passage-${block.id}`,
          'data-passage-id': block.id,
          ...(block.id === refocusId && { tabIndex: -1 }),
        }
        if (block.id === citedPassageId) {
          return (
            <CitedPassage key={block.id} ref={citedRef} onClear={handleClear} {...ids}>
              <PassageText passage={block} />
            </CitedPassage>
          )
        }
        return <PassageText key={block.id} passage={block} elementProps={ids} />
      })}
    </div>
  )
}

export { HandbookBlocks, PassageText }
export type { HandbookBlocksProps, Passage }
