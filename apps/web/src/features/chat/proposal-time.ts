import { formatterFor } from '@/lib/time'

/** The zone the person's own device is in, which "Expires at" is written in. */
export const browserTimeZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone

/** The calendar year it is now in `timeZone`, so sick time in another year names its year. */
export function yearNow(timeZone: string, now: number = Date.now()): number {
  return Number(formatterFor(timeZone, { year: 'numeric' }).format(now))
}
