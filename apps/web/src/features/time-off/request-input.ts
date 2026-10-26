import type { PossibleRequest } from '@/api/generated'
import type { LeaveKind, SubmitChoice } from '@/components/timeoff/choice'

/**
 * The body of a check or a request, from what the form shows: the type, the dates, and the choice
 * the form reports (`resolveChoice`). The check and the send both use it, so they ask the server
 * the same thing. Null while there is nothing to ask: no day picked yet, or hours that aren't a
 * whole number from 1 to 8. A half day is the minutes the API's calendar says it is. The one conversion here is the person's own hours into the API's
 * minutes; no figure is worked out.
 */
export function toPossibleRequest(
  type: LeaveKind,
  start: string | undefined,
  end: string | undefined,
  choice: SubmitChoice,
  halfDayMinutes: number,
): PossibleRequest | null {
  if (start === undefined || end === undefined) return null
  if (choice.howMuch === 'hours' && choice.hours === null) return null
  const partialMinutes =
    choice.howMuch === 'half'
      ? halfDayMinutes
      : choice.howMuch === 'hours'
        ? choice.hours! * 60
        : null
  return { type, startDate: start, endDate: end, partialMinutes }
}
