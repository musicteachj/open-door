import {
  CalendarCheck,
  ChevronDown,
  ChevronUp,
  ClipboardCheck,
  Search,
  ShieldCheck,
  User,
  Users,
  Wrench,
} from 'lucide-react'
import { useId, useState } from 'react'
import type { CitationOut, GuardOut, SectionOut, ToolCallOut } from '@/api/generated'
import { sectionNumber } from '@/components/handbook/labels'
import { cn } from '@/lib/utils'
import { conversationCopy, toolCallLine, toolIcon, type ToolIconKind } from './labels'

type WorkTraceProps = {
  /** What the safety check decided. Null when the turn has no recorded result. */
  guard: GuardOut | null
  toolCalls: ToolCallOut[]
  /**
   * The sections the assistant retrieved. A title or group is null when the conversation's stored
   * sources don't hold it: a cited section falls back to its citation's, and an uncited one shows
   * its number alone.
   */
  sections: SectionOut[]
  /**
   * The answer's citations, already numbered by section (`numberBySection`), which say which
   * sections were cited and as what number.
   */
  citations: CitationOut[]
  /** Opens with the panel showing, for a screen that draws that state. */
  defaultOpen?: boolean
  className?: string
}

const TOOL_ICONS: Record<ToolIconKind, typeof Search> = {
  search: Search,
  profile: User,
  people: Users,
  calendar: CalendarCheck,
  card: ClipboardCheck,
  tool: Wrench,
}

/** The safety line and its note, or null when the guard result says nothing we can stand behind. */
function safetyLine(guard: GuardOut | null): { text: string; note?: string } | null {
  if (guard?.category === 'ordinary') return { text: conversationCopy.safetyOk }
  if (guard?.category === 'sensitive') {
    return { text: conversationCopy.routed, note: conversationCopy.routedNote }
  }
  // A crisis never reaches the model, so it has no trace, and a missing result is not "no concerns".
  return null
}

function SectionRow({ section, citations }: { section: SectionOut; citations: CitationOut[] }) {
  const cited = citations.find((citation) => citation.sectionId === section.sectionId)
  const title = section.title ?? cited?.title ?? null
  const group = section.groupName ?? cited?.groupName ?? null
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-3 gap-y-0.5 border-t border-border-subtle py-1.5 text-ui sm:grid-cols-[64px_minmax(0,1fr)_auto]">
      <span className="row-start-1 text-ink-muted tabular-nums">
        {sectionNumber(section.sectionId)}
      </span>
      <span className="col-span-2 row-start-2 sm:col-span-1 sm:col-start-2 sm:row-start-1">
        {title}
        {title !== null && group !== null && ' · '}
        {group !== null && (
          <span className={title === null ? undefined : 'text-ink-muted'}>{group}</span>
        )}
      </span>
      {cited ? (
        <span className="col-start-2 row-start-1 text-small font-semibold whitespace-nowrap text-ink tabular-nums sm:col-start-3">
          {conversationCopy.citedAs(cited.marker)}
        </span>
      ) : (
        <span className="col-start-2 row-start-1 text-small whitespace-nowrap text-ink-muted sm:col-start-3">
          {conversationCopy.notCited}
        </span>
      )}
    </li>
  )
}

/**
 * "Show your work", for the turn above it: a disclosure button and the panel it opens (from the
 * design's Conversation frames). It renders the two as siblings so `AnswerFooter` can put the button
 * beside "Was this right?" and the panel under the whole row. Collapsed by default, and focus
 * stays on the button when it toggles. The panel is always in the page, hidden, so the button's
 * `aria-controls` always names something real.
 *
 * The lines are what the assistant really did: each tool call worded by `toolLine` (never the raw
 * summary), and each retrieved section with "Cited as N" (the marker number, found by section) or
 * "Not cited".
 */
function WorkTrace({
  guard,
  toolCalls,
  sections,
  citations,
  defaultOpen = false,
  className,
}: WorkTraceProps) {
  const [open, setOpen] = useState(defaultOpen)
  const panelId = useId()
  const toolsId = useId()
  const sectionsId = useId()
  const safety = safetyLine(guard)
  const Chevron = open ? ChevronUp : ChevronDown
  return (
    <>
      <button
        data-slot="work-trace-toggle"
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
        className={cn(
          'inline-flex h-8 cursor-pointer items-center gap-1.5 justify-self-start rounded-sm py-0 pr-2 pl-2.5 text-small font-semibold text-ink hover:bg-neutral-hover sm:col-start-2 sm:row-start-1 sm:justify-self-end',
          className,
        )}
      >
        {conversationCopy.showYourWork}
        <Chevron aria-hidden="true" className="size-4 text-ink-muted" />
      </button>
      <div data-slot="work-trace-panel" id={panelId} hidden={!open} className="col-span-full">
        <div className="flex flex-col gap-4 rounded-lg border border-border bg-surface-sunken px-5 pt-4 pb-4.5">
          {safety && (
            <div className="flex flex-col gap-0.5">
              <p className="m-0 flex items-center gap-2 text-ui font-semibold text-ink">
                <ShieldCheck aria-hidden="true" className="size-4 shrink-0 text-ink-muted" />
                {safety.text}
              </p>
              {safety.note && (
                <p className="m-0 ml-6 text-small text-pretty text-ink-muted">{safety.note}</p>
              )}
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <h3 id={toolsId} className="m-0 text-small font-semibold text-ink">
              {conversationCopy.toolsCalled}
            </h3>
            {toolCalls.length === 0 ? (
              <p className="m-0 text-ui text-ink-muted">{conversationCopy.none}</p>
            ) : (
              <ul aria-labelledby={toolsId} className="m-0 flex list-none flex-col gap-1.5 p-0">
                {toolCalls.map((call, index) => {
                  const Icon = TOOL_ICONS[toolIcon(call.name)]
                  return (
                    // A turn can call one tool twice with the same summary, so the index is the key.
                    <li key={index} className="flex items-center gap-2 text-ui text-ink">
                      <Icon aria-hidden="true" className="size-3.5 shrink-0 text-ink-muted" />
                      {toolCallLine(call)}
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <h3 id={sectionsId} className="m-0 text-small font-semibold text-ink">
              {conversationCopy.sectionsRetrieved}
            </h3>
            {sections.length === 0 ? (
              <p className="m-0 text-ui text-ink-muted">{conversationCopy.none}</p>
            ) : (
              <ul aria-labelledby={sectionsId} className="m-0 list-none p-0">
                {sections.map((section, index) => (
                  <SectionRow
                    // Each section once is the API's promise; the index keeps a repeat from breaking the list.
                    key={`${index}:${section.sectionId}`}
                    section={section}
                    citations={citations}
                  />
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </>
  )
}

export { WorkTrace }
export type { WorkTraceProps }
