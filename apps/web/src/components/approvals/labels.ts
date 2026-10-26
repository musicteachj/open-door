// The approvals words and accessible names, in one tested place (screens 09 and 10). No pronouns:
// a line names the person or the page.
import type { CoverageOut, RequestOut, RequestOutStatus } from '@/api/generated'
import {
  calendarDayIn,
  longDate,
  longRange,
  monthDay,
  monthDayRange,
} from '@/components/timeoff/dates'
import { joinList, typeLabel } from '@/components/timeoff/labels'

export const NOTE_LIMIT_CHARACTERS = 300
/** The live region speaks once the note is this close to the limit. */
export const NOTE_WARN_AT_REMAINING = 20

export const approvalsCopy = {
  teamCoverage: 'Team coverage',
  alsoOff: 'Also off',
  partOfDay: '(part of the day)',
  goBack: 'Go back',
  approve: 'Approve',
  deny: 'Deny',
  approving: 'Approving…',
  denying: 'Denying…',
  seeOnTimeOff: (firstName: string) => `${firstName} will see it on the Time off page.`,
  noteHelper: (firstName: string) =>
    `${firstName} will see this note. Up to ${NOTE_LIMIT_CHARACTERS} characters.`,
  noteLabel: (firstName: string) => `Note to ${firstName} (optional)`,
  charactersLeft: (count: number) => `${count} characters left`,
  noteCount: (count: number) => `${count} of ${NOTE_LIMIT_CHARACTERS}`,
  dialogTitle: (kind: 'approve' | 'deny', name: string) =>
    `${kind === 'approve' ? 'Approve' : 'Deny'} ${name}’s PTO?`,
} as const

/** The first word of a name: "Zara Bautista" is "Zara". */
export function firstNameOf(name: string): string {
  return name.trim().split(/\s+/)[0] ?? name
}

/**
 * The team coverage lines for a request: one line per colleague ("Also off: Vikram Morales,
 * Tuesday, November 10 · PTO"), or the plain "no one else" line. A part of a day says so
 * in words; no minutes become hours here.
 */
export function coverageLines(coverage: CoverageOut[], multiDay: boolean): string[] {
  if (coverage.length === 0) {
    return [`No one else on your team is off ${multiDay ? 'those days' : 'that day'}.`]
  }
  // One line per person. A person off for both kinds of leave has both in the one line.
  return coverage.map((entry) => {
    const parts = (['pto', 'sick'] as const).flatMap((type) => {
      const days = entry.days.filter((day) => day.type === type)
      if (days.length === 0) return []
      const dates = joinList(
        days.map(
          (day) =>
            `${longDate(day.date)}${day.partialMinutes === null ? '' : ` ${approvalsCopy.partOfDay}`}`,
        ),
      )
      return [`${dates} · ${typeLabel(type)}`]
    })
    return `${approvalsCopy.alsoOff}: ${entry.person.name}, ${parts.join(', and ')}`
  })
}

/** "Sent today", "Sent October 17": the day the request was made, in the location's time zone. */
export function sentLine(createdAt: string, today: string, timeZone: string): string {
  const day = calendarDayIn(createdAt, timeZone)
  return `Sent ${day === today ? 'today' : monthDay(day)}`
}

/** "Approve Zara Bautista’s PTO, November 9 to 10": the card button's accessible name. */
export function actionName(
  kind: 'approve' | 'deny',
  person: { name: string },
  start: string,
  end: string,
): string {
  return `${kind === 'approve' ? 'Approve' : 'Deny'} ${person.name}’s PTO, ${monthDayRange(start, end)}`
}

/** The refusal on a card whose request has already moved on. */
export function conflictText(status: RequestOutStatus, firstName: string): string {
  if (status === 'canceled') return `${firstName} canceled this request.`
  if (status === 'approved') return 'This request was already approved.'
  if (status === 'denied') return 'This request was already denied.'
  return 'This request has changed.'
}

/** The dialog's facts: "Monday, November 9 to Tuesday, November 10, 16 hours (2 days)." */
export function decisionFacts(
  request: Pick<RequestOut, 'startDate' | 'endDate' | 'amountLabel'>,
): string {
  return `${longRange(request.startDate, request.endDate)}, ${request.amountLabel}.`
}

export const approvalsPageCopy = {
  title: 'Approvals',
  waiting: 'Waiting for you',
  /** The heading's accessible name: "Waiting for you, 2". With none waiting it is just the words. */
  waitingName: (count: number) => (count > 0 ? `Waiting for you, ${count}` : 'Waiting for you'),
  waitingSubtitle:
    'PTO requests from your direct reports, oldest first. Sick time is recorded, not approved, so it appears only under Coming up.',
  waitingEmpty:
    'Nothing is waiting for you. When someone on your team asks for time off, it shows up here.',
  comingUp: 'Coming up on your team',
  comingUpSubtitle: 'Approved and recorded time off in the next 30 days, soonest first.',
  comingUpEmpty: 'No time off on your team in the next 30 days.',
  recent: 'Recent decisions',
  recentSubtitle: 'Your decisions from the last 90 days, newest first.',
  recentEmpty: 'No decisions in the last 90 days.',
  yourNote: 'Your note',
  loading: 'Loading approvals',
  decisionFailed: 'Couldn’t send that decision. Nothing was changed. Try again in a moment.',
  /** A 404 or 409 that names no reason: trying again can't succeed, so say what happened. */
  changedMeanwhile: 'This request changed in the meantime. The page now shows it as it stands.',
} as const

/** "Approved. Zara will see it on the Time off page." */
export function approvedToast(firstName: string): string {
  return `Approved. ${approvalsCopy.seeOnTimeOff(firstName)}`
}

/** "Denied. Zara will see your note on the Time off page." or, with no note, "...will see it...". */
export function deniedToast(firstName: string, withNote: boolean): string {
  return withNote
    ? `Denied. ${firstName} will see your note on the Time off page.`
    : `Denied. ${approvalsCopy.seeOnTimeOff(firstName)}`
}
