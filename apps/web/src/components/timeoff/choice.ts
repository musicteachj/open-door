import { parseHours } from './parse-hours'
import { timeOffCopy } from './labels'

type HowMuch = 'full' | 'half' | 'hours'
/** How much to request, as the form shows it: `hours` is set only for "Some hours". */
type SubmitChoice = { howMuch: HowMuch; hours: number | null }
type LeaveKind = 'pto' | 'sick'

/** The "how much" choices a type offers: PTO is full or half a day, sick time full or some hours. */
export function howMuchOptionsFor(type: LeaveKind) {
  return [
    { value: 'full', label: timeOffCopy.fullDay },
    type === 'sick'
      ? { value: 'hours', label: timeOffCopy.someHours }
      : { value: 'half', label: timeOffCopy.halfDay },
  ]
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
  const offered = howMuchOptionsFor(type).map((option) => option.value)
  const effective: HowMuch = single && offered.includes(howMuch) ? howMuch : 'full'
  return { howMuch: effective, hours: effective === 'hours' ? parseHours(hours) : null }
}

export type { HowMuch, SubmitChoice, LeaveKind }
