/** The error codes whose approved text sends the visitor to the recorded walkthrough (Phase 9a). */
const OFFERS_WALKTHROUGH: ReadonlySet<string> = new Set([
  'model-unavailable',
  'spend-limit',
  'budget-daily',
])

/** Whether a failed turn's error shows the "Watch the recorded walkthrough" link under its text. */
export function offersWalkthrough(code: string | undefined): boolean {
  return code !== undefined && OFFERS_WALKTHROUGH.has(code)
}
