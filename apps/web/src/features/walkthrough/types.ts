import type { PersonaKey } from '@/api/generated'

// The shape of walkthrough.json, written by the recording (`make walkthrough`, Phase 8 Task 45)
// from the page the video shows, so the transcript's words always match the video.

/** A handbook section an answer cited, shown as plain text ("CA-4.3 · Sick leave"). */
export type WalkthroughSource = { id: string; title: string }

export type WalkthroughExchange =
  /** What the step's persona typed. */
  | { speaker: 'person'; text: string }
  /** The assistant's answer, as it appeared, with the sections it cited. */
  | { speaker: 'ai'; text: string; sources?: readonly WalkthroughSource[] }
  /** The HR panel's fixed text, written by a person: never labeled as the AI's. */
  | { speaker: 'hr-panel'; text: string }

export type WalkthroughStep = {
  /** The tour step's id (features/tour/script.ts). */
  id: string
  title: string
  /** Who the visitor is on this step; null on the end card. */
  persona: PersonaKey | null
  /** The coach mark's words (the end card's first paragraph on the last step). */
  words: string
  exchanges: readonly WalkthroughExchange[]
  /** What the person did after the answer, in a sentence. */
  note?: string
}

export type Walkthrough = {
  /** The day it was recorded, as an ISO date (YYYY-MM-DD). */
  recordedOn: string
  /** The model's name as people say it ("Claude Opus 5.5"). */
  model: string
  durationSeconds: number
  steps: readonly WalkthroughStep[]
}
