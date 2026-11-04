import { Check, CircleAlert, LayoutDashboard, X } from 'lucide-react'
import {
  useEffect,
  useId,
  useRef,
  type ComponentProps,
  type ElementType,
  type ReactNode,
} from 'react'
import type { ConsoleTurnOut, ToolOut } from '@/api/generated'
import { formatCount, toolIcon } from '@/components/assistant/labels'
import { TOOL_ICONS } from '@/components/assistant/tool-icons'
import { EmptyCell } from '@/components/core/empty-cell'
import { outcomeBadgeFor } from '@/components/status/outcome-badges'
import { StatusBadge } from '@/components/timeoff/status-badge'
import { cn } from '@/lib/utils'
import {
  cardActionLabel,
  formatDuration,
  formatFirstToken,
  formatTurnCost,
  refusalLabel,
  toolLabel,
  tracedInputTokens,
  turnTitle,
} from './labels'
import { SafetyLabel } from './safety-label'

type TracePanelProps = {
  /** A timed row. The panel shows only what it carries. */
  turn: ConsoleTurnOut
  timeZone: string
  /** A section's title from its ID, or undefined when it isn't known. */
  sectionTitle: (sectionId: string) => string | undefined
  onClose: () => void
  /** The panel's id, which the row's button names in `aria-controls`. */
  id?: string
  /** The title's element, a dialog's own title component in a sheet. `h2` by default. */
  titleAs?: ElementType
  /** A sheet is the landmark itself, so the panel isn't one there. */
  landmark?: boolean
  /** Moves focus to the title when it opens and when another turn replaces it. On by default. */
  focusOnOpen?: boolean
  /** Whether Escape closes it. A sheet's dialog closes itself, so it turns this off. */
  closeOnEscape?: boolean
  className?: string
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-b border-border-subtle py-4">
      <h3 className="m-0 mb-1.5 text-small font-semibold">{title}</h3>
      {children}
    </section>
  )
}

const Text = ({ children, muted }: { children: ReactNode; muted?: boolean }) => (
  <p className={cn('m-0 text-ui font-normal', muted && 'text-ink-muted')}>{children}</p>
)

const None = () => <Text muted>None</Text>

/** Label and value pairs on a 104 px grid. A mono value is a code. */
function Facts({ rows }: { rows: [string, string | null, boolean?][] }) {
  return (
    <dl className="m-0 p-0">
      {rows.map(([term, value, mono]) => (
        <div
          key={term}
          className="grid grid-cols-[104px_minmax(0,1fr)] gap-x-3 py-[3px] text-ui leading-5 font-normal"
        >
          <dt className="text-ink-muted">{term}</dt>
          <dd className="m-0 break-words tabular-nums">
            {value === null ? (
              <EmptyCell />
            ) : mono ? (
              <code className="font-mono text-[13px]">{value}</code>
            ) : (
              value
            )}
          </dd>
        </div>
      ))}
    </dl>
  )
}

function ToolLine({ tool }: { tool: ToolOut }) {
  const Icon = TOOL_ICONS[toolIcon(tool.name)]
  const Status = tool.ok ? Check : CircleAlert
  return (
    <li className="grid grid-cols-[16px_minmax(0,1fr)_auto_auto] items-start gap-x-2.5 py-2">
      <Icon aria-hidden="true" className="mt-0.5 size-4 text-ink-muted" />
      <span>
        <span className="block text-ui leading-5 font-normal">{toolLabel(tool.name)}</span>
        <code className="block font-mono text-caption leading-[18px] break-words text-ink-muted">
          {tool.name}
        </code>
      </span>
      <span className="text-small whitespace-nowrap text-ink-muted tabular-nums">
        {formatDuration(tool.durationMs)}
      </span>
      <span className="inline-flex items-center gap-1 text-small leading-5 font-semibold whitespace-nowrap">
        <Status
          aria-hidden="true"
          strokeWidth={2}
          className={cn('size-3.5', tool.ok ? 'text-ink-muted' : 'text-danger')}
        />
        {tool.ok ? 'OK' : 'Failed'}
      </span>
    </li>
  )
}

/**
 * One turn's trace, docked at `w-panel` like the passage panel and a full-screen sheet on a phone
 * (TracePanel.jsx). Facts only: never the question, the answer, a tool's inputs, or a refusal's
 * explanation, because the row type carries none. When a turn opens, and when another replaces
 * it, focus moves to the title. Escape and the X call `onClose`; the host puts focus back on the
 * row's button.
 */
function TracePanel({
  turn,
  timeZone,
  sectionTitle,
  onClose,
  id,
  titleAs,
  landmark = true,
  focusOnOpen = true,
  closeOnEscape = true,
  className,
}: TracePanelProps) {
  const Title: ElementType = titleAs ?? 'h2'
  const Root = (landmark ? 'aside' : 'div') as ElementType<ComponentProps<'aside'>>
  const titleId = useId()
  const titleRef = useRef<HTMLHeadingElement>(null)
  const panelRef = useRef<HTMLElement>(null)

  useEffect(() => {
    if (focusOnOpen) titleRef.current?.focus()
  }, [focusOnOpen, turn.id])

  // Escape closes the panel from inside it or from the page body, never from a field elsewhere,
  // during an IME composition, or when something else (an open menu) used the key.
  useEffect(() => {
    if (!closeOnEscape) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented || event.isComposing) return
      const target = event.target
      const inside = target instanceof Node && panelRef.current?.contains(target)
      if (inside || target === document.body) onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [closeOnEscape, onClose])

  const badge = outcomeBadgeFor(turn.outcome)
  const retrieved = turn.sectionsRetrieved ?? []
  const cited = new Set(turn.sectionsCited ?? [])
  const tools = turn.tools ?? []
  const input = tracedInputTokens(turn)
  const fromCache =
    turn.cacheReadTokens > 0 ? ` (${formatCount(turn.cacheReadTokens)} from cache)` : ''
  const servedBy = turn.servedBy
  const last = servedBy[servedBy.length - 1]

  return (
    <Root
      ref={panelRef}
      id={id}
      aria-labelledby={landmark ? titleId : undefined}
      data-slot="trace-panel"
      className={cn(
        'box-border flex h-full min-h-0 w-panel max-w-full flex-col border-l border-border bg-surface-raised text-ink',
        className,
      )}
    >
      <header className="flex flex-none flex-col gap-1.5 border-b border-border-subtle py-3.5 pr-3.5 pb-[18px] pl-6">
        <div className="flex items-center justify-between gap-3">
          <span className="inline-flex items-center gap-2 text-small text-ink-muted">
            <LayoutDashboard aria-hidden="true" className="size-3.5" />
            Turn trace
          </span>
          <button
            type="button"
            aria-label="Close trace"
            onClick={onClose}
            className="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-sm text-ink-muted transition-colors hover:bg-neutral-hover hover:text-ink"
          >
            <X aria-hidden="true" className="size-4" />
          </button>
        </div>
        <Title
          // A dialog's own title brings its own id, which an undefined one here would erase.
          {...(landmark ? { id: titleId } : {})}
          ref={titleRef}
          tabIndex={-1}
          className="m-0 pr-2.5 text-h2 font-semibold text-pretty tabular-nums outline-none"
        >
          {turnTitle(turn, timeZone)}
        </Title>
      </header>
      <div
        // A scrolling region has to take focus so the keyboard can scroll it.
        // oxlint-disable-next-line jsx-a11y/no-noninteractive-tabindex
        tabIndex={0}
        aria-label="Trace details"
        className="min-h-0 flex-1 overflow-y-auto px-6 pb-8 focus-visible:shadow-[inset_0_0_0_2px_var(--color-focus-ring)] focus-visible:outline-none"
      >
        <Section title="Outcome">
          {badge === null ? <None /> : <StatusBadge status={badge} />}
          {turn.refusalCategory !== null && (
            <p className="m-0 mt-2 text-ui font-normal">
              Category: {refusalLabel(turn.refusalCategory)}
            </p>
          )}
        </Section>
        <Section title="Safety check">
          <SafetyLabel
            category={turn.guardCategory}
            ms={turn.guardMs}
            injection={turn.injectionSuspected}
          />
        </Section>
        <Section title="Tools called">
          {tools.length === 0 ? (
            <None />
          ) : (
            <ol className="m-0 list-none p-0">
              {tools.map((tool, index) => (
                <ToolLine key={index} tool={tool} />
              ))}
            </ol>
          )}
        </Section>
        <Section title="Sections retrieved">
          {retrieved.length === 0 ? (
            <None />
          ) : (
            <ul className="m-0 list-none p-0">
              {retrieved.map((sectionId) => {
                const title = sectionTitle(sectionId)
                const isCited = cited.has(sectionId)
                return (
                  <li
                    key={sectionId}
                    className="grid grid-cols-[56px_minmax(0,1fr)_auto] items-baseline gap-x-3 border-t border-border-subtle py-1.5 text-ui leading-5 font-normal"
                  >
                    <span className="text-ink-muted tabular-nums">{sectionId}</span>
                    {title === undefined ? (
                      <span className="text-ink-muted">Not in the current handbook</span>
                    ) : (
                      <span>{title}</span>
                    )}
                    <span
                      className={cn(
                        'text-small whitespace-nowrap',
                        isCited ? 'font-semibold text-ink' : 'text-ink-muted',
                      )}
                    >
                      {isCited ? 'Cited' : 'Not cited'}
                    </span>
                  </li>
                )
              })}
            </ul>
          )}
        </Section>
        <Section title="Card offered">
          {turn.cardAction === null ? <None /> : <Text>{cardActionLabel(turn.cardAction)}</Text>}
        </Section>
        <Section title="Model">
          <Facts
            rows={[
              ['Model', servedBy[0] ?? null, true],
              ['Effort', turn.effort ?? null],
              ['Prompt', turn.promptVersion ?? null, true],
              ['Tools', turn.toolsetVersion ?? null, true],
            ]}
          />
          {turn.fallback && last !== undefined && servedBy.length > 1 && (
            <p className="m-0 mt-1 text-small text-ink-muted">
              Served by <code className="font-mono text-[13px]">{last}</code> after a fallback
            </p>
          )}
        </Section>
        <Section title="Tokens">
          <Facts
            rows={[
              ['Input', `${formatCount(input)}${fromCache}`],
              ['Output', formatCount(turn.outputTokens)],
              ['Cache writes', formatCount(turn.cacheWriteTokens)],
            ]}
          />
        </Section>
        <Section title="Cost">
          <p className="m-0 text-body leading-[22px] font-semibold tabular-nums">
            {formatTurnCost(turn.costUsd)}
          </p>
          <p className="m-0 mt-1 text-small text-ink-muted">Includes the safety check</p>
        </Section>
        <Section title="Timings">
          <Facts
            rows={[
              ['Safety check', turn.guardMs === null ? null : formatDuration(turn.guardMs)],
              ['First token', formatFirstToken(turn.firstTextMs)],
              ['Total', turn.totalMs === null ? null : formatDuration(turn.totalMs)],
            ]}
          />
        </Section>
      </div>
    </Root>
  )
}

export { TracePanel }
export type { TracePanelProps }
