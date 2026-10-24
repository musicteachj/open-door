// The time-off form's words and accessible names, in one tested place (the Copy section of
// docs/design/screens/08-time-off/notes.md). A component calls these instead of building its own
// string. No pronouns: a line names the person or the page.
import type {
  DrawOut,
  FailureOut,
  LeaveTypeName,
  ProblemOut,
  RequestOutStatus,
  RuleRefOut,
  SkippedDay,
} from '@/api/generated'
import { sectionNumber } from '@/components/handbook/labels'
import { calendarDayIn, isoWeekday, longDate, monthDay, shortRange } from './dates'
import { splitLabel } from './label-parts'

/** The five states a request can show. The API's `pending` is `waiting` here. */
export type TimeOffStatus = 'waiting' | 'approved' | 'denied' | 'recorded' | 'canceled'

const STATUS_WORDS: Record<TimeOffStatus, string> = {
  waiting: 'Waiting for approval',
  approved: 'Approved',
  denied: 'Denied',
  recorded: 'Recorded',
  canceled: 'Canceled',
}

export const timeOffCopy = {
  typeLabel: 'Type',
  typePto: 'PTO',
  typeSick: 'Sick time',
  datesLabel: 'Dates',
  datesPlaceholder: 'Pick a day or a range',
  howMuchLabel: 'How much',
  fullDay: 'Full day',
  // Fixed copy, not a figure the browser works out: a PTO half day is 240 minutes by the spec.
  halfDay: 'Half day (4 hours)',
  someHours: 'Some hours',
  hoursLabel: 'Hours',
  hoursHint: '1 to 8 hours',
  hoursError: 'Enter a whole number from 1 to 8.',
  fewerHours: 'Fewer hours',
  moreHours: 'More hours',
  previousMonth: 'Previous month',
  nextMonth: 'Next month',
  done: 'Done',
  legendOff: 'Not on your schedule',
  legendHoliday: 'Company holiday',
  legendToday: 'Today',
  pastLabelPto: 'Past days can’t be picked for PTO',
  hintEmpty: 'Pick a day, or a first and last day.',
  hintInProgress: 'Now pick the last day. For one day, choose Done.',
} as const

export function statusLabel(status: TimeOffStatus): string {
  return STATUS_WORDS[status]
}

/** The legend's line for sick time, which can reach back: "Sick time can go back 30 days, to September 20". */
export function pastLabelSick(lookbackDays: number, earliest: string): string {
  return `Sick time can go back ${lookbackDays} days, to ${monthDay(earliest)}`
}

/** The tooltip on a holiday's day. */
export function holidayTip(name: string): string {
  return `${name}, company holiday`
}

type DayLabelInput = {
  day: string
  /** The holiday's name, when the day is a company holiday. */
  holiday?: string
  off?: boolean
  today?: boolean
  disabled?: boolean
}

/** A day cell's accessible name: its date, then every mark it carries, in one fixed order. */
export function dayLabel({ day, holiday, off, today, disabled }: DayLabelInput): string {
  const parts = [longDate(day)]
  if (holiday) parts.push(holidayTip(holiday))
  if (off) parts.push('not on your schedule')
  if (today) parts.push('today')
  if (disabled) parts.push('not available')
  return parts.join(', ')
}

/** The picker's status line under the grid. */
export function pickerHint({
  start,
  end,
  inProgress = false,
}: {
  start?: string
  end?: string
  inProgress?: boolean
}): string {
  if (inProgress) return timeOffCopy.hintInProgress
  if (!start) return timeOffCopy.hintEmpty
  return `Selected: ${shortRange(start, end ?? start)}`
}

/** "a", "a and b", "a, b, and c". */
export function joinList(items: string[]): string {
  if (items.length <= 2) return items.join(' and ')
  return `${items.slice(0, -1).join(', ')}, and ${items[items.length - 1]}`
}

type RuleText = Pick<RuleRefOut, 'sectionId' | 'title'>

/** A source chip's text: "Handbook §4.1 · Paid time off", "Handbook CA-4.3 · Sick leave". */
export function ruleChipLabel(rule: RuleText): string {
  return `Handbook ${sectionNumber(rule.sectionId)} · ${rule.title}`
}

/** A source chip's accessible name: "Source: Handbook §4.1, Paid time off". */
export function ruleChipName(rule: RuleText): string {
  return `Source: Handbook ${sectionNumber(rule.sectionId)}, ${rule.title}`
}

export const previewCopy = {
  title: 'What this uses',
  sources: 'Sources',
  empty: 'Pick dates to see what this uses.',
  nothingCounted: 'None of these days are on your schedule, so there’s nothing to request.',
  alreadyBooked: 'Already booked',
  // Spoken before each line, never shown.
  counted: 'Counted:',
  skipped: 'Skipped:',
  blocked: 'Can’t be counted:',
} as const

const WEEKDAY_PLURALS = [
  'Mondays',
  'Tuesdays',
  'Wednesdays',
  'Thursdays',
  'Fridays',
  'Saturdays',
  'Sundays',
]

/**
 * One line for many days off the person's schedule: "Saturdays and Sundays in these dates aren't
 * on your schedule", naming only the weekdays that were skipped, in week order.
 */
export function foldedScheduleLine(days: string[]): string {
  const present = new Set(days.map(isoWeekday))
  const names = WEEKDAY_PLURALS.filter((_, index) => present.has(index + 1))
  return `${joinList(names)} in these dates aren’t on your schedule`
}

/** A skipped day's line: a holiday by name, or a day off the person's schedule. */
export function skippedLine(skipped: SkippedDay): string {
  if (skipped.reason === 'not scheduled') return `${longDate(skipped.day)} isn’t on your schedule`
  return `${longDate(skipped.day)} is ${skipped.reason}, a company holiday`
}

/**
 * "this year" or "in 2027" for a sick draw. "This year" only when the request draws on one year and
 * that year is the current one (or the current year isn't known); otherwise the year's number, so
 * a request across New Year never says "this year" about either half.
 */
function sickYearPhrase(draws: DrawOut[], draw: DrawOut, thisYear?: number): string {
  if (draw.year === null) return 'this year'
  const current = draws.length === 1 && (thisYear === undefined || draw.year === thisYear)
  return current ? 'this year' : `in ${draw.year}`
}

/**
 * What is left after a request, one line per draw. PTO has one draw ("84 hours (10.5 days) left
 * after this"). Sick time speaks in hours, "this year" for one draw in the current year (or when
 * `thisYear` isn't known) and the year's number otherwise.
 */
export function leftLines(type: LeaveTypeName, draws: DrawOut[], thisYear?: number): string[] {
  if (type === 'pto')
    return draws.slice(0, 1).map((draw) => `${draw.availableAfterLabel} left after this`)
  return draws.map(
    (draw) =>
      `${splitLabel(draw.availableAfterLabel).hours} of sick leave left ${sickYearPhrase(draws, draw, thisYear)}`,
  )
}

export const formCopy = {
  title: 'Request time off',
  close: 'Close',
  submitPto: 'Request time off',
  submitSick: 'Record sick time',
  submittingPto: 'Requesting…',
  submittingSick: 'Recording…',
  cancel: 'Cancel',
  sickNote: 'Sick time is recorded right away, with no approval.',
  shortNotice: 'More than 3 days usually needs 2 weeks’ notice. You can still request it.',
  approverNote: (name: string) => `${name}, your manager, reviews PTO requests.`,
} as const

type ProblemContext = {
  type: LeaveTypeName
  draws: DrawOut[]
  /** The whole request's amount label, for PTO's "This request needs". */
  amountLabel?: string | null
  overlappingDays?: string[]
  thisYear?: number
}

/**
 * The refusal under the form for one problem. Two codes get a sentence with the figures from the
 * API's own labels (the draw that runs short, the days that clash); any other shows the API's
 * fixed text as it is.
 */
export function problemText(problem: ProblemOut, context: ProblemContext): string {
  if (problem.code === 'not-enough' && context.draws.length > 0) {
    const draw = context.draws.find((item) => item.availableAfterMinutes < 0) ?? context.draws[0]!
    if (context.type === 'pto') {
      const needs = context.amountLabel ?? draw.amountLabel
      return `You have ${draw.availableBeforeLabel} available. This request needs ${needs}.`
    }
    const when = sickYearPhrase(context.draws, draw, context.thisYear)
    return `You have ${splitLabel(draw.availableBeforeLabel).hours} of sick leave left ${when}. This request needs ${splitLabel(draw.amountLabel).hours}.`
  }
  if (problem.code === 'overlaps' && context.overlappingDays?.length) {
    return `You already have time off on ${joinList(context.overlappingDays.map(longDate))}.`
  }
  return problem.text
}

/** What a failed confirm says on a card. `verb` is book, record, approve, deny, or cancel. */
export function failureText(failure: FailureOut, verb: string): string {
  if (failure.code === 'overlaps' && failure.dates?.length) {
    return `Couldn’t ${verb} this: you already have time off on ${joinList(failure.dates.map(longDate))}. Nothing was changed.`
  }
  return `Couldn’t ${verb} this. ${failure.text} Nothing was changed.`
}

/** "Approved today", "Denied October 5": a team row's decision line. */
export function decisionLine(
  status: Extract<RequestOutStatus, 'approved' | 'denied'>,
  decidedAt: string | null,
  today: string,
  timeZone: string,
): string | null {
  if (decidedAt === null) return null
  const word = status === 'approved' ? 'Approved' : 'Denied'
  const day = calendarDayIn(decidedAt, timeZone)
  return `${word} ${day === today ? 'today' : monthDay(day)}`
}

export const balanceCopy = {
  ptoLabel: 'PTO available',
  sickLabel: 'Sick leave available this year',
  earned: 'Earned to date',
  taken: 'Taken',
  booked: 'Booked',
  waiting: 'Waiting for approval',
  granted: 'Granted on January 1',
  used: 'Used',
  renews: 'Renews January 1.',
  next: (hours: string, date: string) => `Next: ${hours} on ${monthDay(date)}`,
  canSave: (hours: string) => `You can save up to ${hours}.`,
  pausedNext: (limit: string) => `Next: paused at the ${limit} limit`,
  pausedNotice: (hours: string) =>
    `You’ve saved ${hours}, the most you can hold, so you won’t earn more PTO until you take some time off.`,
} as const

/** The leave type as a word: "PTO", "Sick time", or "sick time" in the middle of a sentence. */
export function typeLabel(
  type: LeaveTypeName,
  { lower = false }: { lower?: boolean } = {},
): string {
  if (type === 'pto') return timeOffCopy.typePto
  return lower ? timeOffCopy.typeSick.toLowerCase() : timeOffCopy.typeSick
}

/** "62 hours (7.75 days) available now": the balance on a denial, which gives the hours back. */
export function availableNow(label: string): string {
  return `${label} available now`
}

/** "84 hours (10.5 days) available after this": the balance line on a card and in a dialog. */
export function availableAfter(label: string): string {
  return `${label} available after this`
}
