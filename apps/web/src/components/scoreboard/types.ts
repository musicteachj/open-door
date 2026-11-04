// The shape of `src/generated/scoreboard.json`, which `make scoreboard` writes from the committed
// run boards (evals/scoreboard_gen.py, ADR 0017). There is no generated type for it, so this is
// written by hand, and `isScoreboard` is the guard the test runs on the real file: a generator
// change that breaks the shape fails CI.

export type ScoreboardFigure = {
  label: string
  value: number
  display: string
}

export type ScoreboardSet = {
  key: string
  name: string
  /** "Full run, Nov 3, 2026": what the figures are from. Null for a set that was not run. */
  detail: string | null
  notRun: boolean
  headline: ScoreboardFigure | null
  /** The worst trial's figure. `value` is null when there were no trials. */
  lowest: { value: number | null; display: string } | null
  /** Other figures, one per line. */
  also: string[]
  facts: {
    /** The model that served the set. */
    model?: string | null
    /** The assistant, safety check, and judge, on the Q&A set. */
    models?: { assistant?: string; guard?: string; judge?: string } | null
    itemsPerTrial?: number
    trials?: number
    date?: string
  } | null
}

export type ScoreboardHistoryRow = {
  stamp: string
  /** "Nov 3, 2026, 14:00 UTC". */
  date: string
  model: string | null
  qa: string | null
  unanswerable: string | null
  redteam: string | null
  actions: string | null
  judge: string | null
  cost: string | null
}

export type ScoreboardData = {
  schema: 1
  sets: ScoreboardSet[]
  /** Full runs, oldest first. */
  history: ScoreboardHistoryRow[]
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)
const isString = (value: unknown): value is string => typeof value === 'string'
const isNullableString = (value: unknown) => value === null || isString(value)

function isFigure(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.label) &&
    typeof value.value === 'number' &&
    isString(value.display)
  )
}

function isLowest(value: unknown): boolean {
  return (
    isRecord(value) &&
    (value.value === null || typeof value.value === 'number') &&
    isString(value.display)
  )
}

/**
 * The facts a set carries: when present, `itemsPerTrial` and `trials` are numbers, `model` is a
 * string or null, `date` is a string, and `models` are strings.
 */
function isFacts(value: unknown): boolean {
  if (!isRecord(value)) return false
  if (value.itemsPerTrial !== undefined && typeof value.itemsPerTrial !== 'number') return false
  if (value.model !== undefined && !isNullableString(value.model)) return false
  if (value.trials !== undefined && typeof value.trials !== 'number') return false
  if (value.date !== undefined && typeof value.date !== 'string') return false
  const models = value.models
  if (models === undefined || models === null) return true
  return isRecord(models) && Object.values(models).every(isString)
}

function isSet(value: unknown): value is ScoreboardSet {
  return (
    isRecord(value) &&
    isString(value.key) &&
    isString(value.name) &&
    isNullableString(value.detail) &&
    typeof value.notRun === 'boolean' &&
    (value.headline === null || isFigure(value.headline)) &&
    (value.lowest === null || isLowest(value.lowest)) &&
    Array.isArray(value.also) &&
    value.also.every(isString) &&
    (value.facts === null || isFacts(value.facts))
  )
}

const HISTORY_FIELDS = ['model', 'qa', 'unanswerable', 'redteam', 'actions', 'judge', 'cost']

function isHistoryRow(value: unknown): value is ScoreboardHistoryRow {
  return (
    isRecord(value) &&
    isString(value.stamp) &&
    isString(value.date) &&
    HISTORY_FIELDS.every((field) => isNullableString(value[field]))
  )
}

/** Whether `data` has the scoreboard's shape (schema 1). */
export function isScoreboard(data: unknown): data is ScoreboardData {
  return (
    isRecord(data) &&
    data.schema === 1 &&
    Array.isArray(data.sets) &&
    data.sets.every(isSet) &&
    Array.isArray(data.history) &&
    data.history.every(isHistoryRow)
  )
}
