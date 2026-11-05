import type { ConsoleMetricsOut } from '@/api/generated'
import { ConsoleTile, type ConsoleTileProps } from './console-tile'
import {
  cardActionPlural,
  formatDuration,
  formatPercent,
  formatSpend,
  formatTarget,
  formatTurnCost,
} from './labels'

type ConsoleTilesProps = {
  /** Leave out while the figures load. */
  metrics?: ConsoleMetricsOut
  loading?: boolean
  /** A handbook section's title from its ID, or undefined when it isn't known. */
  sectionTitle: (sectionId: string) => string | undefined
}

const turnsWord = (count: number) => `${count} ${count === 1 ? 'turn' : 'turns'}`
const SMALL = 'Small sample'

/** "9 turns · Small sample", or just "31 turns". */
const turnsFoot = (turns: number, small: boolean) =>
  small ? `${turnsWord(turns)} · ${SMALL}` : turnsWord(turns)

const TITLES = [
  'Time to first token',
  'Safety check time',
  'Cost per answered question',
  'Escalation rate',
  'Refusals and fallbacks',
  'Said the handbook doesn’t cover it',
  'Cards confirmed by a person',
  'Possible prompt injections',
] as const

/** The eight tiles' props from the metrics, in the order the design draws them. */
const CARD_ACTION_ORDER = ['timeoff.request', 'timeoff.decide', 'timeoff.cancel']

/** The three card rows, always, with 0 for an action the audit log has no row for. */
function cardRows(confirmed: ConsoleMetricsOut['cardsConfirmed']): [string, string][] {
  const counts = new Map(confirmed.map(({ action, count }) => [action, count]))
  const extra = confirmed.map(({ action }) => action).filter((a) => !CARD_ACTION_ORDER.includes(a))
  return [...CARD_ACTION_ORDER, ...extra].map((action) => [
    cardActionPlural(action),
    String(counts.get(action) ?? 0),
  ])
}

function tileProps(
  m: ConsoleMetricsOut,
  sectionTitle: (id: string) => string | undefined,
): ConsoleTileProps[] {
  const empty = m.turns === 0
  const none = (title: string, extra: Partial<ConsoleTileProps> = {}): ConsoleTileProps => ({
    title,
    state: 'empty',
    ...extra,
  })
  const { firstToken, safetyCheck, cost, escalation, refusals, notFound, injections } = m

  const tiles: ConsoleTileProps[] = []
  tiles.push(
    empty || firstToken.p50Ms === null
      ? none(TITLES[0])
      : {
          title: TITLES[0],
          pre: 'Median',
          figure: formatDuration(firstToken.p50Ms),
          lines: [
            ...(firstToken.p95Ms === null
              ? []
              : [`95th percentile ${formatDuration(firstToken.p95Ms)}`]),
            `Target ${formatTarget(firstToken.targetMs)}`,
          ],
          foot: turnsFoot(firstToken.sampleSize, firstToken.smallSample),
        },
  )
  tiles.push(
    empty || safetyCheck.p95Ms === null
      ? none(TITLES[1])
      : {
          title: TITLES[1],
          pre: '95th percentile',
          figure: formatDuration(safetyCheck.p95Ms),
          lines: [`Target ${formatTarget(safetyCheck.targetMs)}`],
          foot: turnsFoot(safetyCheck.sampleSize, safetyCheck.smallSample),
        },
  )
  const spend = `Sandbox spend ${formatSpend(cost.sandboxSpendUsd, cost.sandboxCapUsd)}`
  tiles.push(
    empty || cost.perAnsweredQuestionUsd === null
      ? none(TITLES[2], { spend })
      : {
          title: TITLES[2],
          figure: formatTurnCost(cost.perAnsweredQuestionUsd),
          lines: [
            `${cost.answeredCount} answered ${cost.answeredCount === 1 ? 'question' : 'questions'}`,
          ],
          spend,
          foot: cost.smallSample ? SMALL : undefined,
        },
  )
  tiles.push(
    empty || escalation.rate === null
      ? none(TITLES[3])
      : {
          title: TITLES[3],
          figure: formatPercent(escalation.rate),
          lines: [
            `${escalation.flaggedCount} of ${turnsWord(escalation.turns)} flagged by the safety check`,
          ],
          foot: escalation.smallSample ? SMALL : undefined,
        },
  )
  tiles.push(
    empty || refusals.rate === null
      ? none(TITLES[4])
      : {
          title: TITLES[4],
          figure: formatPercent(refusals.rate),
          lines: [`${refusals.affectedCount} of ${turnsWord(refusals.turns)}`],
          foot: refusals.smallSample ? SMALL : undefined,
        },
  )
  tiles.push(
    empty
      ? none(TITLES[5])
      : {
          title: TITLES[5],
          figure: String(notFound.count),
          lines: [`of ${turnsWord(notFound.turns)}`],
          closest: notFound.sections.map(({ sectionId, count }) => {
            const title = sectionTitle(sectionId)
            return `${sectionId}${title === undefined ? '' : ` ${title}`} (${count})`
          }),
          foot: notFound.smallSample ? SMALL : undefined,
        },
  )
  tiles.push(
    empty
      ? none(TITLES[6])
      : {
          title: TITLES[6],
          rows: cardRows(m.cardsConfirmed),
          foot: 'From the audit log',
        },
  )
  tiles.push(
    empty
      ? none(TITLES[7])
      : {
          title: TITLES[7],
          figure: String(injections.count),
          lines: [`of ${turnsWord(injections.turns)}`],
          foot: injections.smallSample ? SMALL : undefined,
        },
  )
  return tiles
}

/**
 * The console's eight tiles from `GET /console/metrics` (.od-tiles): auto-fill columns of at
 * least 220 px, so four across at 1080 px, two beside the docked trace, and one on a phone.
 */
function ConsoleTiles({ metrics, loading = false, sectionTitle }: ConsoleTilesProps) {
  const tiles: ConsoleTileProps[] =
    loading || metrics === undefined
      ? TITLES.map((title) => ({ title, state: 'loading' as const }))
      : tileProps(metrics, sectionTitle)
  return (
    <div
      data-slot="console-tiles"
      className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4"
    >
      {tiles.map((tile) => (
        <ConsoleTile key={tile.title} {...tile} />
      ))}
    </div>
  )
}

export { ConsoleTiles }
export type { ConsoleTilesProps }
