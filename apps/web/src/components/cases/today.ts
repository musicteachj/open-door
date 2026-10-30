import { formatterFor } from '@/lib/time'

/** Today's calendar date ("2026-10-26") in `timeZone`: the viewer's location, not the browser's. */
export function todayIn(timeZone: string, now: Date = new Date()): string {
  const parts = formatterFor(timeZone, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now)
  const part = (type: string) => parts.find((p) => p.type === type)?.value ?? ''
  return `${part('year')}-${part('month')}-${part('day')}`
}
