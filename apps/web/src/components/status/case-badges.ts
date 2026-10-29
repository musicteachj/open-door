// The case status badges' type and words. They live apart from the cases folder so the shared
// status badge doesn't depend on it.

/** The six badge values for a case: three for the person (My cases), three for HR. */
export type CaseBadge =
  'case-sent' | 'case-reviewing' | 'case-finished' | 'case-new' | 'case-in-review' | 'case-closed'

export const CASE_BADGE_WORDS: Record<CaseBadge, string> = {
  'case-sent': 'Sent to HR',
  'case-reviewing': 'HR is reviewing',
  'case-finished': 'HR has finished its review',
  'case-new': 'New',
  'case-in-review': 'In review',
  'case-closed': 'Closed',
}

export function isCaseBadge(value: string): value is CaseBadge {
  return Object.hasOwn(CASE_BADGE_WORDS, value)
}
