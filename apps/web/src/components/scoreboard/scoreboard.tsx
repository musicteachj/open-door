import { useId, type ReactNode } from 'react'
import { EmptyCell } from '@/components/core/empty-cell'
import { modelDisplayName } from '@/lib/models'
import { cn } from '@/lib/utils'
import type { ScoreboardData, ScoreboardHistoryRow, ScoreboardSet } from './types'

type ScoreboardProps = {
  data: ScoreboardData
  /** The heading's level. The history's heading is one below it. */
  headingLevel?: 2 | 3
  className?: string
}

const MODEL_LABELS = [
  ['Assistant', 'assistant'],
  ['safety check', 'guard'],
  ['judge', 'judge'],
] as const

const REPLAY_NOTE =
  "These figures come from recorded eval runs. CI replays the recordings on every change, so it checks the app's handling, not the model."

/** "Assistant claude-opus-5-5 · safety check … · judge …", from the Q&A set's facts. */
function ModelsLine({ data }: { data: ScoreboardData }) {
  const models = data.sets.find((set) => set.key === 'qa')?.facts?.models
  const parts = MODEL_LABELS.flatMap(([label, key]) => {
    const id = models?.[key]
    return id ? [[label, id] as const] : []
  })
  if (parts.length === 0) return null
  return (
    <p className="m-0 mt-1.5 text-ui leading-[22px] font-normal text-pretty text-ink-muted">
      {parts.map(([label, id], index) => (
        <span key={label}>
          {index > 0 && ' · '}
          {label} <code className="font-mono text-[13px] text-ink">{id}</code>
        </span>
      ))}
    </p>
  )
}

/** The size of the full set, from the Q&A set's facts, as the README's generator words it. */
function fullSetSize(data: ScoreboardData): string {
  const items = data.sets.find((set) => set.key === 'qa')?.facts?.itemsPerTrial
  return items ? `${items} items in the full set` : 'a few hundred items'
}

/** The day the Actions figure first appears in the history, unless it was there from the start. */
function actionsJoinedOn(history: ScoreboardHistoryRow[]): string | null {
  const index = history.findIndex((row) => row.actions)
  if (index <= 0) return null
  // "Oct 26, 2026, 15:22 UTC" without its time of day, so the year stays (as the README generator
  // writes it). A date with no comma is used whole.
  const date = history[index]!.date
  const comma = date.lastIndexOf(',')
  return comma === -1 ? date : date.slice(0, comma)
}

/** A table that scrolls sideways inside its own container, so the page never does. */
function Scroller({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section
      // A scrolling region has to take focus so the keyboard can scroll it.
      // oxlint-disable-next-line jsx-a11y/no-noninteractive-tabindex
      tabIndex={0}
      aria-label={label}
      className="relative overflow-x-auto overflow-y-hidden focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus-ring"
    >
      {children}
    </section>
  )
}

const TABLE = 'w-full min-w-160 table-fixed border-collapse tabular-nums'
const HEAD = 'px-3 py-2.5 text-left text-small leading-5 font-normal text-ink-muted'

/** One set's row: the name and what it is from, its headline, its lowest trial, and the rest. */
function SetRow({ set }: { set: ScoreboardSet }) {
  return (
    <tr className="border-b border-border-subtle align-top">
      <th scope="row" className="p-4 pr-3 text-left font-normal">
        <span className="block text-body leading-[22px] font-semibold">{set.name}</span>
        {set.detail && <span className="block text-small text-ink-muted">{set.detail}</span>}
      </th>
      {set.notRun ? (
        <td colSpan={3} className="px-3 py-4 text-ui leading-[22px] font-normal text-ink-muted">
          Not measured yet.
        </td>
      ) : (
        <>
          <td className="px-3 py-4">
            {set.headline === null ? (
              <span className="block text-ui leading-[30px] font-normal text-ink-muted">
                Not measured yet.
              </span>
            ) : (
              <>
                <span className="block text-[24px] leading-[30px] font-semibold tracking-[-0.01em]">
                  {set.headline.display}
                </span>
                <span className="block text-small text-ink-muted">{set.headline.label}</span>
              </>
            )}
          </td>
          <td
            className={cn(
              'px-3 py-4',
              set.lowest === null || set.lowest.value === null
                ? 'text-ui leading-[22px] font-normal text-ink-muted'
                : 'text-body leading-[30px]',
            )}
          >
            {set.lowest === null ? <EmptyCell /> : set.lowest.display}
          </td>
          <td className="px-3 py-4 text-ui leading-[22px] font-normal text-pretty">
            {set.also.length === 0 ? (
              <EmptyCell />
            ) : (
              set.also.map((line) => (
                <span key={line} className="block">
                  {line}
                </span>
              ))
            )}
          </td>
        </>
      )}
    </tr>
  )
}

const HISTORY_COLUMNS = [
  'Date',
  'Model',
  'Q&A',
  'Unanswerable',
  'Red team',
  'Actions',
  'Judge',
  'Cost',
]

function HistoryRow({ run }: { run: ScoreboardHistoryRow }) {
  const cells = [run.qa, run.unanswerable, run.redteam, run.actions, run.judge, run.cost]
  const cell = 'p-3 text-right font-normal'
  return (
    <tr className="border-b border-border-subtle align-top">
      <th scope="row" className="p-3 text-left font-normal whitespace-nowrap">
        {run.date}
      </th>
      <td className="p-3 text-left font-normal">
        {run.model === null ? <EmptyCell hidden="Not in the set" /> : modelDisplayName(run.model)}
      </td>
      {cells.map((value, index) => (
        <td key={index} className={cell}>
          {value === null ? <EmptyCell hidden="Not in the set" /> : value}
        </td>
      ))}
    </tr>
  )
}

/** The set rows alone: Set, Result, Lowest trial, and Other figures. */
function ScoreboardSetsTable({ sets }: { sets: ScoreboardSet[] }) {
  return (
    <Scroller label="Eval sets">
      <table className={TABLE}>
        <caption className="sr-only">Eval sets</caption>
        <colgroup>
          <col style={{ width: '22%' }} />
          <col style={{ width: '20%' }} />
          <col style={{ width: '16%' }} />
          <col style={{ width: '42%' }} />
        </colgroup>
        <thead>
          <tr className="border-b border-border">
            {['Set', 'Result', 'Lowest trial', 'Other figures'].map((label) => (
              <th key={label} scope="col" className={HEAD}>
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sets.map((set) => (
            <SetRow key={set.key} set={set} />
          ))}
        </tbody>
      </table>
    </Scroller>
  )
}

/**
 * The eval scoreboard (Scoreboard.jsx): each set's headline with its lowest trial, the history of
 * full runs, and the two plain lines, always visible. Its figures come from the generated
 * `scoreboard.json`, so it renders even when the sandbox data fails to load. No chart, and no
 * color on any figure. Each table scrolls inside its own region (640 px minimum).
 */
function Scoreboard({ data, headingLevel = 2, className }: ScoreboardProps) {
  const id = useId()
  const Heading = `h${headingLevel}` as const
  const SubHeading = `h${headingLevel + 1}` as 'h3' | 'h4'
  const joined = actionsJoinedOn(data.history)
  // Newest first, as the design draws it; the file holds oldest first.
  const runs = [...data.history].reverse()
  return (
    <section
      aria-labelledby={`${id}-h`}
      data-slot="scoreboard"
      className={cn('min-w-0 text-ink', className)}
    >
      <Heading id={`${id}-h`} className="m-0 text-h2">
        Eval scoreboard
      </Heading>
      <ModelsLine data={data} />
      <p className="m-0 mt-0.5 text-ui leading-[22px] font-normal text-ink-muted">
        Three trials per set unless noted.
      </p>
      <div className="mt-5">
        <ScoreboardSetsTable sets={data.sets} />
      </div>
      <SubHeading className="m-0 mt-10 text-body leading-[22px] font-semibold">
        History of full runs
      </SubHeading>
      <div className="mt-3">
        <Scroller label="History of full runs">
          <table className={cn(TABLE, 'text-ui leading-5 font-normal')}>
            <caption className="sr-only">History of full runs</caption>
            <colgroup>
              <col style={{ width: '22%' }} />
              <col style={{ width: '15%' }} />
              <col style={{ width: '9%' }} />
              <col style={{ width: '13%' }} />
              <col style={{ width: '10%' }} />
              <col style={{ width: '9%' }} />
              <col style={{ width: '9%' }} />
              <col style={{ width: '13%' }} />
            </colgroup>
            <thead>
              <tr className="border-b border-border">
                {HISTORY_COLUMNS.map((label, index) => (
                  <th key={label} scope="col" className={cn(HEAD, index > 1 && 'text-right')}>
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <HistoryRow key={run.stamp} run={run} />
              ))}
            </tbody>
          </table>
        </Scroller>
      </div>
      {joined !== null && (
        <p className="m-0 mt-2.5 px-3 text-small text-ink-muted">
          Actions joined the full set on {joined}.
        </p>
      )}
      <div className="mt-7 flex max-w-190 flex-col gap-1.5 border-t border-border-subtle pt-4">
        <p className="m-0 text-ui leading-[22px] font-normal text-pretty">{REPLAY_NOTE}</p>
        <p className="m-0 text-ui leading-[22px] font-normal text-pretty">
          The sets are small ({fullSetSize(data)}), so a single item can move a figure by more than
          a point.
        </p>
      </div>
    </section>
  )
}

export { Scoreboard, ScoreboardSetsTable }
export type { ScoreboardProps }
