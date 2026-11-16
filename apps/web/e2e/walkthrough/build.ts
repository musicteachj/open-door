// The recording's pure parts (Phase 8, Task 45), unit-tested by build.test.ts: how long a coach
// mark is held, how a step's stored turns become its transcript, and the notes under a step.
// record.ts drives the browser and calls these.

import type { WalkthroughExchange, WalkthroughSource } from '../../src/features/walkthrough/types'

/** What record.ts reads of a turn from the API's conversation (the same data the page renders). */
export type RecordedTurn = {
  question: string
  /** `running` until the turn has ended (`completed`, `stopped`, `failed`, `crisis`, ...). */
  status: string
  answerText: string
  citations: { sectionId: string; title: string; offsetUtf16?: number }[]
  escalation: { kind: string; message: string } | null
}

const READ_BASE_MS = 4000
const WORDS_PER_SECOND_ADDED = 15

/** How long to hold words on screen: about 4 s, plus 1 s for every 15 words. */
export function holdMs(text: string): number {
  const words = text.split(/\s+/).filter(Boolean).length
  return Math.round(READ_BASE_MS + (1000 * words) / WORDS_PER_SECOND_ADDED)
}

/**
 * An answer's Markdown without its links: the walkthrough is public, so a link to the handbook or
 * the directory would only reach the landing. The link's words stay.
 */
export function withoutLinks(markdown: string): string {
  return markdown.replace(/\[([^\]]+)\]\([^)\s]*\)/g, '$1')
}

function sourcesOf(citations: RecordedTurn['citations']): WalkthroughSource[] {
  const inTextOrder = [...citations].sort((a, b) => (a.offsetUtf16 ?? 0) - (b.offsetUtf16 ?? 0))
  const seen = new Set<string>()
  const sources: WalkthroughSource[] = []
  for (const citation of inTextOrder) {
    if (seen.has(citation.sectionId)) continue
    seen.add(citation.sectionId)
    sources.push({ id: citation.sectionId, title: citation.title })
  }
  return sources
}

/**
 * A step's turns as its transcript: each question, then the HR panel's fixed text when the turn
 * was routed to a person, or else the answer as stored, with the sections it cited.
 */
export function exchangesOf(turns: readonly RecordedTurn[]): WalkthroughExchange[] {
  return turns.flatMap((turn): WalkthroughExchange[] => {
    const asked: WalkthroughExchange = { speaker: 'person', text: turn.question }
    if (turn.escalation) {
      return [asked, { speaker: 'hr-panel', text: turn.escalation.message }]
    }
    const text = withoutLinks(turn.answerText).trim()
    if (text === '') throw new Error(`The turn "${turn.question}" has no answer to record.`)
    const sources = sourcesOf(turn.citations)
    return [asked, sources.length > 0 ? { speaker: 'ai', text, sources } : { speaker: 'ai', text }]
  })
}

/** The notes under a step, in the words the owner approved on 2026-11-15. */
export const NOTES: Readonly<Record<string, string>> = {
  'book-day-off': 'Priya confirmed the card. The request went to Marcus Bell.',
  'decide-as-manager': 'Marcus confirmed. Priya’s request is approved.',
  sensitive: 'Priya sent a confidential case to HR in her own words.',
}

/** Step 8's note, quoting the summary the AI wrote of Priya's case. */
export function summaryNote(summary: string): string {
  return `Dana opened Priya’s case. The AI’s summary: “${summary.trim()}” Priya’s own words stayed hidden.`
}

/** YYYY-MM-DD in the machine's own time zone, built from its parts (no locale's date format). */
export function localIsoDate(date: Date): string {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-')
}
