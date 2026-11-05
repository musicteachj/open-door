import type { ReactNode } from 'react'
import { ConsoleError } from '@/components/console/console-error'
import { ConsoleTile } from '@/components/console/console-tile'
import { ConsoleTiles } from '@/components/console/console-tiles'
import { ConsoleTraceHost } from '@/components/console/console-trace-host'
import { SafetyLabel } from '@/components/console/safety-label'
import { TracePanel } from '@/components/console/trace-panel'
import { TurnTable } from '@/components/console/turn-table'
import { Scoreboard, ScoreboardSetsTable } from '@/components/scoreboard/scoreboard'
import { isScoreboard } from '@/components/scoreboard/types'
import { OUTCOME_BADGE_WORDS, type OutcomeBadge } from '@/components/status/outcome-badges'
import { StatusBadge } from '@/components/timeoff/status-badge'
import type { ConsoleTurnOut } from '@/api/generated'
import generated from '@/generated/scoreboard.json'
import { Group, Section } from '../gallery-parts'
import {
  CONSOLE_ZONE,
  DAY_METRICS,
  DAY_TURNS,
  EMPTY_METRICS,
  FILLED_METRICS,
  sectionTitle,
  T_0914_REFUSED,
  T_0948_FAILED,
  T_1002_FALLBACK,
  T_1031_ANSWERED,
  T_1033_CARD,
  T_1038_INJECTION,
  T_ABANDONED,
  T_FLAGGED,
} from '../fixtures/console'

// The AI Ops console's parts (screen 13) in every state the design draws, and the shared eval
// scoreboard. Nothing is fetched: the components are given the sample day (fixtures/console.ts).
// The live console at the end is the one place that holds state: open a row, open another to swap
// it, Escape or the X to close.

if (!isScoreboard(generated)) throw new Error('The generated scoreboard has an unexpected shape.')
const BOARD = generated

const noop = () => {}
const BADGES = Object.keys(OUTCOME_BADGE_WORDS) as OutcomeBadge[]

/**
 * The console's content width, 1080 px, shrinking with the window. The gallery's column is 760 px,
 * so this breaks out of it, centered, to show the design's width.
 */
function Wide({ children }: { children: ReactNode }) {
  return (
    <div className="relative left-1/2 w-[min(1080px,calc(100vw-4rem))] min-w-0 shrink-0 -translate-x-1/2">
      {children}
    </div>
  )
}

function Trace({ turn }: { turn: ConsoleTurnOut }) {
  return (
    <TracePanel
      turn={turn}
      timeZone={CONSOLE_ZONE}
      sectionTitle={sectionTitle}
      onClose={noop}
      focusOnOpen={false}
      closeOnEscape={false}
      className="h-auto"
    />
  )
}

const table = (turns: ConsoleTurnOut[], extra: Partial<Parameters<typeof TurnTable>[0]> = {}) => (
  <Wide>
    <TurnTable turns={turns} timeZone={CONSOLE_ZONE} {...extra} />
  </Wide>
)

function ConsoleSections() {
  return (
    <>
      <Group title="Console: outcomes and safety check">
        <Section id="console-outcome-badges" title="Outcome badges">
          {BADGES.map((badge) => (
            <StatusBadge key={badge} status={badge} />
          ))}
        </Section>
        <Section id="console-safety-labels" title="Safety check labels">
          <SafetyLabel category="ordinary" />
          <SafetyLabel category="ordinary" ms={980} />
          <SafetyLabel category="ordinary" injection />
          <SafetyLabel category="ordinary" injection stacked />
          <SafetyLabel category={null} />
        </Section>
      </Group>

      <Group title="Console: tiles">
        <Section id="console-tile-normal" title="Tile, counts list">
          <div className="w-64">
            <ConsoleTile
              title="Cards confirmed by a person"
              rows={[
                ['Time-off requests', '1'],
                ['Decisions', '1'],
                ['Cancellations', '0'],
              ]}
              foot="From the audit log"
            />
          </div>
        </Section>
        <Section id="console-tile-small-sample" title="Tile, small sample">
          <div className="w-64">
            <ConsoleTile
              title="Time to first token"
              pre="Median"
              figure="1.6 s"
              lines={['95th percentile 2.2 s', 'Target 3 s']}
              foot="9 turns · Small sample"
            />
          </div>
        </Section>
        <Section id="console-tile-above-target" title="Tile, above target (neutral, same ink)">
          <div className="w-64">
            <ConsoleTile
              title="Safety check time"
              pre="95th percentile"
              figure="980 ms"
              lines={['Target 800 ms']}
              foot="9 turns · Small sample"
            />
          </div>
        </Section>
        <Section id="console-tile-no-turns" title="Tile, no turns yet (spend kept)">
          <div className="w-64">
            <ConsoleTile
              title="Cost per answered question"
              state="empty"
              spend="Sandbox spend $0.00 of $1.00 cap"
            />
          </div>
        </Section>
        <Section id="console-tile-sections" title="Tile, sections search came closest with">
          <div className="w-64">
            <ConsoleTile
              title="Said the handbook doesn’t cover it"
              figure="2"
              lines={['of 31 turns']}
              closest={['4.1 Paid time off (2)', '5.2 Parental leave (1)']}
            />
          </div>
          <div className="w-64">
            <ConsoleTile
              title="Said the handbook doesn’t cover it"
              figure="0"
              lines={['of 9 turns']}
              closest={[]}
              foot="Small sample"
            />
          </div>
        </Section>
        <Section id="console-tile-loading" title="Tile, loading">
          <div className="w-64">
            <ConsoleTile title="Escalation rate" state="loading" />
          </div>
        </Section>
        <Section id="console-tiles-day" title="Eight tiles, the sample day (1080 px)">
          <Wide>
            <ConsoleTiles metrics={DAY_METRICS} sectionTitle={sectionTitle} />
          </Wide>
        </Section>
        <Section id="console-tiles-filled" title="Eight tiles, 31 turns with sections named">
          <Wide>
            <ConsoleTiles metrics={FILLED_METRICS} sectionTitle={sectionTitle} />
          </Wide>
        </Section>
        <Section id="console-tiles-empty" title="Eight tiles, a new sandbox">
          <Wide>
            <ConsoleTiles metrics={EMPTY_METRICS} sectionTitle={sectionTitle} />
          </Wide>
        </Section>
        <Section id="console-tiles-loading" title="Eight tiles, loading">
          <Wide>
            <ConsoleTiles loading sectionTitle={sectionTitle} />
          </Wide>
        </Section>
      </Group>

      <Group title="Console: turn table">
        <Section id="console-table-rows" title="Turn table, the sample day">
          {table(DAY_TURNS)}
        </Section>
        <Section id="console-table-selected" title="Turn table, a row selected (as when open)">
          {table([T_1031_ANSWERED, T_1033_CARD, T_1038_INJECTION], {
            selectedId: T_1033_CARD.id,
          })}
        </Section>
        <Section id="console-table-flagged" title="Turn table, flagged and abandoned rows">
          {table([T_FLAGGED, T_ABANDONED])}
        </Section>
        <Section id="console-table-loading" title="Turn table, loading">
          {table([], { loading: true })}
        </Section>
        <Section id="console-table-empty" title="Turn table, empty">
          {table([], { onAskQuestion: noop, onTakeTour: noop })}
        </Section>
        <Section id="console-error" title="Error">
          <Wide>
            <ConsoleError reference="c41e8b07" onRetry={noop} />
          </Wide>
        </Section>
      </Group>

      <Group title="Console: turn trace">
        <Section id="console-trace-answered" title="Trace, answered">
          <Trace turn={T_1031_ANSWERED} />
        </Section>
        <Section id="console-trace-card" title="Trace, card offered">
          <Trace turn={T_1033_CARD} />
        </Section>
        <Section id="console-trace-injection" title="Trace, possible prompt injection">
          <Trace turn={T_1038_INJECTION} />
        </Section>
        <Section id="console-trace-refused" title="Trace, refused by the model">
          <Trace turn={T_0914_REFUSED} />
        </Section>
        <Section id="console-trace-fallback" title="Trace, served after a fallback">
          <Trace turn={T_1002_FALLBACK} />
        </Section>
        <Section id="console-trace-failed-tool" title="Trace, a tool that failed">
          <Trace turn={T_0948_FAILED} />
        </Section>
      </Group>

      <Group title="Console: live">
        <Section id="console-live" title="The console, live (1080 px)">
          <Wide>
            <ConsoleTraceHost
              turns={DAY_TURNS}
              timeZone={CONSOLE_ZONE}
              sectionTitle={sectionTitle}
              before={<ConsoleTiles metrics={DAY_METRICS} sectionTitle={sectionTitle} />}
            />
          </Wide>
        </Section>
      </Group>

      <Group title="Eval scoreboard">
        <Section id="console-scoreboard" title="Scoreboard, whole">
          <Wide>
            <Scoreboard data={BOARD} />
          </Wide>
        </Section>
        <Section id="console-scoreboard-rows" title="Scoreboard set rows, with figures and not run">
          <Wide>
            <ScoreboardSetsTable
              sets={[
                ...BOARD.sets.filter((set) => set.key === 'quality' || set.key === 'retrieval'),
                {
                  key: 'not-run',
                  name: 'Fairness',
                  detail: null,
                  notRun: true,
                  headline: null,
                  lowest: null,
                  also: [],
                  facts: null,
                },
              ]}
            />
          </Wide>
        </Section>
      </Group>
    </>
  )
}

export { ConsoleSections }
