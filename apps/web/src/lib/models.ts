// claude-opus-5-5, claude-opus-5, and the dated ids (claude-sonnet-4-20250514). A date is dropped.
const MODEL_ID = /^claude-(opus|sonnet|haiku)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?$/

/** "claude-opus-5-5" as "Claude Opus 5.5". An id this doesn't know comes back unchanged. */
export function modelDisplayName(modelId: string): string {
  const match = MODEL_ID.exec(modelId)
  if (!match) return modelId
  const [, family, major, minor] = match
  const version = minor === undefined ? major : `${major}.${minor}`
  return `Claude ${family![0]!.toUpperCase()}${family!.slice(1)} ${version}`
}
