import { parseHours } from './parse-hours'
import { halfDayChoice, timeOffCopy } from './labels'

type HowMuch = 'full' | 'half' | 'hours'
/** How much to request, as the form shows it: `hours` is set only for "Some hours". */
type SubmitChoice = { howMuch: HowMuch; hours: number | null }
type LeaveKind = 'pto' | 'sick'

/** The "how much" values a type offers: PTO is full or half a day, sick time full or some hours. */
export function howMuchValuesFor(type: LeaveKind): HowMuch[] {
  return type === 'sick' ? ['full', 'hours'] : ['full', 'half']
}

/**
 * The "how much" choices a type offers, labeled. `halfDayLabel` is the API's own words for the
 * half day ("4 hours").
 */
export function howMuchOptionsFor(type: LeaveKind, halfDayLabel: string) {
  const labels: Record<HowMuch, string> = {
    full: timeOffCopy.fullDay,
    half: halfDayChoice(halfDayLabel),
    hours: timeOffCopy.someHours,
  }
  return howMuchValuesFor(type).map((value) => ({ value, label: labels[value] }))
}

/**
 * What the form reports for the inputs it shows: a range is always Full day, and so is a
 * how-much the type does not offer. Hours count only for "Some hours" on one sick day, and are
 * null when the text is not a whole number from 1 to 8. The form and the page that checks the
 * same inputs both read it here, so the check and the send can never disagree.
 */
export function resolveChoice(
  type: LeaveKind,
  start: string | undefined,
  end: string | undefined,
  howMuch: HowMuch,
  hours: string,
): SubmitChoice {
  const single = start !== undefined && start === end
  const offered = howMuchValuesFor(type)
  const effective: HowMuch = single && offered.includes(howMuch) ? howMuch : 'full'
  return { howMuch: effective, hours: effective === 'hours' ? parseHours(hours) : null }
}

export type { HowMuch, SubmitChoice, LeaveKind }
