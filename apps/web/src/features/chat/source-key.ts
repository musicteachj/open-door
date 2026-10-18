import type { CitationOut } from '@/api/generated'
import { isPathSegment } from '@/features/handbook/path-segment'

// A passage's ID is only unique within its section: the API's CA-4.3 and 4.3 both have a "p1". The
// conversation page names a source by both, "CA-4.3~p1", in the URL (`?source=`) and in the
// components that say which passage is open, so two sections' p1 are never mixed up.

export function sourceKey(sectionId: string, passageId: string): string {
  return `${sectionId}~${passageId}`
}

/** The section and passage a `?source=` value names, or null if it names neither. */
export function parseSourceKey(
  value: string | null,
): { sectionId: string; passageId: string } | null {
  if (value === null) return null
  const at = value.indexOf('~')
  if (at === -1) return null
  const sectionId = value.slice(0, at)
  const passageId = value.slice(at + 1)
  if (!isPathSegment(sectionId) || !isPathSegment(passageId)) return null
  return { sectionId, passageId }
}

const keyed = new WeakMap<CitationOut[], CitationOut[]>()

/**
 * The citations with each `passageId` replaced by its source key, so the components (which compare
 * `passageId` to say what is open) and the URL agree. Applying it twice changes nothing. The same
 * array in gives the same array out.
 */
export function withSourceKeys(citations: CitationOut[]): CitationOut[] {
  const known = keyed.get(citations)
  if (known !== undefined) return known
  const result = citations.map((citation) => ({
    ...citation,
    passageId: citation.passageId.includes('~')
      ? citation.passageId
      : sourceKey(citation.sectionId, citation.passageId),
  }))
  keyed.set(citations, result)
  return result
}
