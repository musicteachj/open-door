// The console's outcome badges: their type, words, and the API outcomes they stand for. Apart from
// the status badge, like the case badges, so the badge doesn't depend on the console folder.

/** The seven badge values for a turn's outcome (screen 13). */
export type OutcomeBadge =
  | 'outcome-answered'
  | 'outcome-not-covered'
  | 'outcome-refused'
  | 'outcome-stopped'
  | 'outcome-failed'
  | 'outcome-cap'
  | 'outcome-safety-unavailable'

export const OUTCOME_BADGE_WORDS: Record<OutcomeBadge, string> = {
  'outcome-answered': 'Answered',
  'outcome-not-covered': 'Said the handbook doesn’t cover it',
  'outcome-refused': 'Refused by the model',
  'outcome-stopped': 'Stopped by the person',
  'outcome-failed': 'Failed',
  'outcome-cap': 'Spending cap reached',
  'outcome-safety-unavailable': 'Safety check unavailable',
}

const BY_API_OUTCOME: Record<string, OutcomeBadge> = {
  answered: 'outcome-answered',
  not_found: 'outcome-not-covered',
  refused: 'outcome-refused',
  stopped: 'outcome-stopped',
  failed: 'outcome-failed',
  budget: 'outcome-cap',
  guard_unavailable: 'outcome-safety-unavailable',
}

export function isOutcomeBadge(value: string): value is OutcomeBadge {
  return Object.hasOwn(OUTCOME_BADGE_WORDS, value)
}

/** The badge for a console row's `outcome`, or null for a value the console doesn't know. */
export function outcomeBadgeFor(outcome: string | null): OutcomeBadge | null {
  return outcome !== null && Object.hasOwn(BY_API_OUTCOME, outcome)
    ? BY_API_OUTCOME[outcome]!
    : null
}
