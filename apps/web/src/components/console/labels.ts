// The console's words and number formats, in one tested place (screen 13's notes, "Build
// decisions"). Everything here works from what a console row carries: never a name or any text.
import type { ConsoleTurnOut } from '@/api/generated'
import { formatCount } from '@/components/assistant/labels'
import { OUTCOME_BADGE_WORDS, outcomeBadgeFor } from '@/components/status/outcome-badges'
import { formatMonthDay, formatterFor, plainSpaces } from '@/lib/time'

const TOOL_LABELS: Record<string, string> = {
  get_time_off_balance: 'Checked time off',
  list_time_off_requests: 'Checked time off',
  check_time_off: 'Checked time off',
  propose_time_off_request: 'Prepared a confirm card',
  propose_time_off_decision: 'Prepared a confirm card',
  propose_cancel_time_off: 'Prepared a confirm card',
  find_people: 'Looked up the directory',
  search_handbook: 'Searched the handbook',
  get_my_profile: 'Read the profile',
  get_my_cases: 'Checked cases',
  list_cases: 'Checked cases',
}

/** A tool's neutral label ("Checked time off"). The trace shows the tool's own name beside it. */
export function toolLabel(name: string): string {
  return Object.hasOwn(TOOL_LABELS, name) ? TOOL_LABELS[name]! : 'Used a tool'
}

const CARD_ACTIONS: Record<string, { one: string; many: string }> = {
  'timeoff.request': { one: 'Time-off request', many: 'Time-off requests' },
  'timeoff.decide': { one: 'Time-off decision', many: 'Decisions' },
  'timeoff.cancel': { one: 'Time-off cancellation', many: 'Cancellations' },
}

/** The card a turn offered, by its action: "Time-off request". An unknown action shows as is. */
export function cardActionLabel(action: string): string {
  return Object.hasOwn(CARD_ACTIONS, action) ? CARD_ACTIONS[action]!.one : action
}

/** The same action as a row of the "Cards confirmed by a person" tile. */
export function cardActionPlural(action: string): string {
  return Object.hasOwn(CARD_ACTIONS, action) ? CARD_ACTIONS[action]!.many : action
}

const ROLES: Record<string, string> = { employee: 'Employee', manager: 'Manager', hr: 'HR' }

export function roleLabel(role: string): string {
  return Object.hasOwn(ROLES, role) ? ROLES[role]! : role
}

/** "general_harms" as "general harms". */
export function refusalLabel(category: string): string {
  return category.replaceAll('_', ' ')
}

/** A turn's cost to three decimals: "$0.021". */
export function formatTurnCost(usd: number): string {
  return `$${usd.toFixed(3)}`
}

/** The sandbox's spend against its cap, to two decimals: "$0.21 of $1.00 cap". */
export function formatSpend(spendUsd: number, capUsd: number): string {
  return `$${spendUsd.toFixed(2)} of $${capUsd.toFixed(2)} cap`
}

/** Under a second in ms ("980 ms"), otherwise seconds with one decimal ("1.6 s"). */
export function formatDuration(ms: number): string {
  const whole = Math.round(ms)
  return whole < 1000 ? `${whole} ms` : `${(ms / 1000).toFixed(1)} s`
}

/** A target in the fewest digits: "3 s", "800 ms", "2.5 s". */
export function formatTarget(ms: number): string {
  return ms >= 1000 && ms % 1000 === 0 ? `${ms / 1000} s` : formatDuration(ms)
}

/** The first token's time, or "No answer text" when the turn never produced any. */
export function formatFirstToken(ms: number | null): string {
  return ms === null ? 'No answer text' : formatDuration(ms)
}

/**
 * A rate as a whole percent: "11%". A rate above zero that rounds to 0 is "Under 1%", and one
 * short of 1 that would round up to 100 is "Over 99%", so only a true 1 reads "100%".
 */
export function formatPercent(rate: number): string {
  if (rate > 0 && rate < 0.005) return 'Under 1%'
  if (rate >= 0.995 && rate < 1) return 'Over 99%'
  return `${Math.round(rate * 100)}%`
}

/** A timestamp's clock time in the zone: "10:31 AM". The zone's name is said once, in the header. */
export function rowTime(timestamp: string, timeZone: string): string {
  return plainSpaces(
    formatterFor(timeZone, { hour: 'numeric', minute: '2-digit' }).format(new Date(timestamp)),
  )
}

/** The zone's short name on that date: "MDT" in October, "MST" in December. */
export function zoneAbbreviation(timeZone: string, at: string | Date): string {
  const parts = formatterFor(timeZone, { timeZoneName: 'short' }).formatToParts(new Date(at))
  return parts.find((part) => part.type === 'timeZoneName')?.value ?? timeZone
}

const noonOf = (isoDate: string) => new Date(`${isoDate}T12:00:00Z`)

/** "Monday, October 26 · 9 turns". The count includes flagged rows. */
export function dayHeading(isoDate: string, turns: number): string {
  const day = formatterFor('UTC', { weekday: 'long', month: 'long', day: 'numeric' }).format(
    noonOf(isoDate),
  )
  return `${day} · ${turns} ${turns === 1 ? 'turn' : 'turns'}`
}

/** "Oct 26", a calendar date. */
export function shortDay(isoDate: string): string {
  return formatMonthDay(isoDate)
}

/** Whether a row is a timed one: it has the facts a button and a trace need. */
export function isTimed(turn: ConsoleTurnOut): turn is ConsoleTurnOut & { occurredAt: string } {
  return !turn.flagged && turn.occurredAt !== null
}

/**
 * The row button's name in two parts, so the visible time comes first: the button shows `time`
 * and a visually hidden `hidden` follows ("10:31 AM" then ", Employee, Oakland, CA, Answered").
 */
export function turnName(turn: ConsoleTurnOut, timeZone: string): { time: string; hidden: string } {
  const outcome = outcomeBadgeFor(turn.outcome)
  const words = [
    turn.askerRole === null ? null : roleLabel(turn.askerRole),
    turn.askerLocation,
    outcome === null ? null : OUTCOME_BADGE_WORDS[outcome],
  ].filter((word) => word !== null)
  return { time: rowTime(turn.occurredAt!, timeZone), hidden: words.map((w) => `, ${w}`).join('') }
}

/** The trace's title: "10:31 AM · Employee · Oakland, CA". */
export function turnTitle(turn: ConsoleTurnOut, timeZone: string): string {
  return [
    rowTime(turn.occurredAt!, timeZone),
    turn.askerRole === null ? null : roleLabel(turn.askerRole),
    turn.askerLocation,
  ]
    .filter((part) => part !== null)
    .join(' · ')
}

/**
 * The input the trace shows: the API's `inputTokens` is the plain input only, so the tokens read
 * from the cache are added back ("Input 12,400 (10,200 from cache)"). Cache writes are a separate
 * row, so they are not counted here.
 */
export function tracedInputTokens(turn: ConsoleTurnOut): number {
  return turn.inputTokens + turn.cacheReadTokens
}

/**
 * Every input token a turn used, cache reads and writes included. A redacted row has no
 * breakdown, so its one line says this total.
 */
export function totalInputTokens(turn: ConsoleTurnOut): number {
  return tracedInputTokens(turn) + turn.cacheWriteTokens
}

/** The one line a redacted row shows: its date, tokens, cost, and whichever timings it has. */
export function redactedFacts(turn: ConsoleTurnOut): string {
  const parts = [
    shortDay(turn.occurredOn),
    `${formatCount(totalInputTokens(turn))} input tokens`,
    `${formatCount(turn.outputTokens)} output`,
    formatTurnCost(turn.costUsd),
  ]
  if (turn.guardMs !== null) parts.push(`safety check ${formatDuration(turn.guardMs)}`)
  if (turn.firstTextMs !== null) parts.push(`first token ${formatDuration(turn.firstTextMs)}`)
  if (turn.totalMs !== null) parts.push(`total ${formatDuration(turn.totalMs)}`)
  return parts.join(' · ')
}
