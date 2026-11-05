/**
 * The `data-tour` values the guided tour points at. The components that carry them and the tour's
 * script both read this one map, so a name can't drift. A component spreads `tourTarget(...)`.
 */
export const TOUR_TARGETS = {
  composer: 'composer',
  sourceChip: 'source-chip',
  confirm: 'confirm',
  openCase: 'open-case',
  caseSend: 'case-send',
  caseRow: 'case-row',
  caseSummary: 'case-summary',
  flaggedRow: 'flagged-row',
} as const

export type TourTargetName = (typeof TOUR_TARGETS)[keyof typeof TOUR_TARGETS]

/** The attribute a tour target carries, as props to spread onto its element. */
export const tourTarget = (name: TourTargetName) => ({ 'data-tour': name }) as const
