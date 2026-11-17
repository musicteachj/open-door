import type { Walkthrough } from './types'
import data from './walkthrough.json'

/** The recording's transcript. The JSON is checked against this type and the tour's script by
 * recording.test.ts. */
export const WALKTHROUGH = data as Walkthrough

/** Where the production image serves the video and its poster (apps/web/public/media). */
export const VIDEO_SRC = '/media/walkthrough.mp4'
export const POSTER_SRC = '/media/walkthrough-poster.jpg'

/** "2 min 30 s", "2 min", or "45 s". */
export function formatDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.round(totalSeconds))
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  if (minutes === 0) return `${rest} s`
  return rest === 0 ? `${minutes} min` : `${minutes} min ${rest} s`
}

/** "October 26, 2026" from "2026-10-26", the same in every time zone. */
export function formatRecordedOn(isoDate: string): string {
  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'long',
    timeZone: 'UTC',
  }).format(new Date(`${isoDate}T00:00:00Z`))
}

/** "Recorded October 26, 2026 · Claude Opus 5.5 · 2 min 30 s · No sound" (screen 16). */
export function metadataLine(
  walkthrough: Pick<Walkthrough, 'recordedOn' | 'model' | 'durationSeconds'>,
) {
  return [
    `Recorded ${formatRecordedOn(walkthrough.recordedOn)}`,
    walkthrough.model,
    formatDuration(walkthrough.durationSeconds),
    'No sound',
  ].join(' · ')
}
