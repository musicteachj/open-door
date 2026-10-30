// The case form's words that a person at Open Door wrote and the app owns (headings, hints, field
// errors, button labels). The fixed, hashed texts do not live here: the form's five lines, the
// panel text, and the sent line come from the API as props (apps/api/app/modules/cases/texts.py).
import type { PageLink } from '@/lib/page-link'
import type { Category, QueueFilter, Status } from '@/api/generated'
import { formatCount } from '@/components/assistant/labels'
import type { CaseBadge } from '@/components/status/case-badges'
import { dayInZone, formatCalendarDate } from './case-dates'
import { CASE_LIMIT_CHARACTERS } from './validate'

export const CATEGORY_OPTIONS: { value: Category; label: string }[] = [
  { value: 'harassment_discrimination', label: 'Harassment or discrimination' },
  { value: 'safety', label: 'Workplace safety' },
  { value: 'medical_accommodation', label: 'Medical or accommodation' },
  { value: 'pay', label: 'Pay concern' },
  { value: 'other', label: 'Something else, or not sure' },
]

export function categoryLabel(category: Category): string {
  return CATEGORY_OPTIONS.find((option) => option.value === category)?.label ?? category
}

/** "46 of 4,000 characters", and at the limit the line that says to shorten it. */
export function countLine(count: number): string {
  const of = `${formatCount(count)} of ${formatCount(CASE_LIMIT_CHARACTERS)} characters`
  return count >= CASE_LIMIT_CHARACTERS ? `${of}. Shorten it to send.` : of
}

export const caseCopy = {
  openButton: 'Open a confidential case',
  heading: 'Open a confidential case',
  categoryLabel: 'What is this about?',
  wordsLabel: 'Your words',
  hint: 'Say what happened, when, where, and who was involved, as much as you know.',
  // For a short reply ("yes, that's what happened") that raised the panel.
  shortHint: 'Add what happened, when, where, and who was involved, as much as you know.',
  beforeYouSend: 'Before you send',
  send: 'Send to HR',
  sending: 'Sending…',
  tryAgain: 'Try again',
  notNow: 'Not now',
  noCategory: 'Choose what this is about.',
  noWords: 'Add your words before sending.',
  personalData:
    'That looks like a Social Security or card number. Please take it out before sending.',
  sendFailed: 'Your case wasn’t sent. Please try again.',
  viewInMyCases: 'View in My cases',
  viewYourCases: 'View your cases',
  writeToHr: 'Write to HR',
} as const

export type CaseSentLink = PageLink

/** The link under the sent line in the conversation, for a person. */
export const MY_CASES_LINK: CaseSentLink = { to: '/my-cases', label: caseCopy.viewInMyCases }

/** "Write to HR", for a page that offers it. HR has no My cases, so HR's pages never pass it. */
export const WRITE_TO_HR_LINK: CaseSentLink = { to: '/my-cases', label: caseCopy.writeToHr }

/** The link after the limit line in the panel: the design's build decision. */
export const YOUR_CASES_LINK: CaseSentLink = { to: '/my-cases', label: caseCopy.viewYourCases }

export type { CaseBadge }

const PERSON_BADGES: Record<Status, CaseBadge> = {
  new: 'case-sent',
  in_review: 'case-reviewing',
  closed: 'case-finished',
}

const HR_BADGES: Record<Status, CaseBadge> = {
  new: 'case-new',
  in_review: 'case-in-review',
  closed: 'case-closed',
}

/** The badge the person who opened a case sees: "Sent to HR", "HR is reviewing", and so on. */
export function personBadge(status: Status): CaseBadge {
  return PERSON_BADGES[status]
}

/** The badge HR sees: "New", "In review", "Closed". */
export function hrBadge(status: Status): CaseBadge {
  return HR_BADGES[status]
}

/** The timeline's line for the safety check's crisis routing, which comes from the case's screening. */
export const CRISIS_TIMELINE_LINE = 'The safety check routed it to crisis text'

/** The first word of a name: "Priya Raman" is "Priya". */
export function firstNameOf(name: string): string {
  return name.trim().split(/\s+/)[0] ?? name
}

/** The list's empty line on My cases. */
export const EMPTY_CASE_LIST = 'You haven’t sent HR a case.'

/**
 * The date line on a My cases row: "HR replies by Wed, Oct 28" (new), "Since Tue, Oct 27" (in
 * review), "Finished Fri, Oct 30" (closed). The reply-by date is a calendar date; a status date is
 * a timestamp shown in the viewer's zone.
 */
export function personDateLine(
  c: { status: Status; replyBy: string; statusChangedAt: string },
  timeZone: string,
): string {
  if (c.status === 'new') return `HR replies by ${formatCalendarDate(c.replyBy)}`
  const day = dayInZone(c.statusChangedAt, timeZone)
  return c.status === 'in_review' ? `Since ${day}` : `Finished ${day}`
}

/** The queue's filter: the API's four, and "all" (no filter at all). */
export type QueueFilterValue = QueueFilter | 'all'

export const QUEUE_FILTERS: { value: QueueFilterValue; label: string }[] = [
  { value: 'open', label: 'Open' },
  { value: 'new', label: 'New' },
  { value: 'in_review', label: 'In review' },
  { value: 'closed', label: 'Closed' },
  { value: 'all', label: 'All' },
]

export const QUEUE_EMPTY: Record<QueueFilterValue, string> = {
  open: 'No open cases.',
  new: 'No new cases. A case appears here as soon as someone sends one.',
  in_review: 'No cases in review.',
  closed: 'No closed cases.',
  all: 'No cases yet.',
}

/** The fact under a case the safety check sent to crisis text. A fact in muted ink, not an alert. */
export const CRISIS_FACT = 'The safety check routed this message to crisis text.'

/**
 * The queue's reply line. A new case counts toward its reply-by date: "Reply due today", "Reply
 * due Wed, Oct 28", or "Reply was due Mon, Oct 26". `today` and `replyBy` are calendar dates, so
 * they compare as text and no time zone can move them. Later states say since when.
 */
export function replyLine(
  c: { status: Status; replyBy: string; statusChangedAt: string },
  today: string,
  timeZone: string,
): string {
  if (c.status === 'in_review') return `In review since ${dayInZone(c.statusChangedAt, timeZone)}`
  if (c.status === 'closed') return `Closed ${dayInZone(c.statusChangedAt, timeZone)}`
  if (c.replyBy === today) return 'Reply due today'
  const date = formatCalendarDate(c.replyBy)
  return c.replyBy < today ? `Reply was due ${date}` : `Reply due ${date}`
}

/** The AI tag on the summary: the same small bordered mark the assistant's answers carry. */
export const AI_TAG = 'AI'

/** The detail page's words that Open Door's team wrote (the Copy sections of screen 12's notes). */
export const detailCopy = {
  summaryTitle: 'AI summary',
  summaryMeta: 'Written by Open Door’s AI to be neutral, with no recommendation',
  summaryPending: 'Writing the summary…',
  summaryFailed: 'No AI summary. Read the person’s words below.',
  summaryCrisis: 'No AI summary for this case. The safety check routed it to crisis text.',
  tryAgain: 'Try again',
  readsRecorded: 'Your reads of this case are recorded in its timeline.',
  replyByEmail: 'Reply by email or in person. Open Door doesn’t send messages.',
  department: 'Department',
  location: 'Location',
  email: 'Email',
  timeline: 'Timeline',
  changeStatus: 'Change the status',
  startReview: 'Start review',
  closeCase: 'Close case',
  caseClosed: 'This case is closed.',
  ownCase: 'You opened this case, so you can’t act on it or read it here.',
  wordsOf: (first: string) => `${first}’s words`,
  wordsHidden: (first: string) =>
    `${first}’s words are hidden. Opening them is recorded in this case’s timeline.`,
  wordsFailed: (first: string) => `${first}’s words couldn’t be opened. Please try again.`,
  showWords: (first: string) => `Show ${first}’s words`,
  hideWords: (first: string) => `Hide ${first}’s words`,
  readFirst: (first: string) => `Read ${first}’s words before changing the status.`,
  reviewTitle: 'Start review of this case?',
  reviewBody: (first: string) => `${first} will see “HR is reviewing” in My cases.`,
  closeTitle: 'Close this case?',
  closeBody: (first: string) =>
    `${first} will see “HR has finished its review.” A closed case can’t be reopened in Open Door.`,
  statusFailed: 'The status wasn’t changed. Please try again.',
  statusMoved: 'This case’s status changed. The page shows it as it is now.',
  cancel: 'Cancel',
  starting: 'Starting…',
  closing: 'Closing…',
} as const

/** The pages' own words: My cases (people) and the queue (HR). */
export const pagesCopy = {
  myCasesTitle: 'My cases',
  myCasesIntro:
    'Cases you’ve sent to HR. Only the HR team can open them in Open Door, and they’re stored encrypted.',
  myCasesLoading: 'Loading your cases',
  casesTitle: 'Cases',
  casesIntro:
    'Confidential. Only the HR team can open these cases, and every read of a case’s text is recorded.',
  loadMoreFailed: 'More cases couldn’t be loaded. Please try again.',
  casesLoading: 'Loading the cases',
  caseLoading: 'Loading the case',
  loadMore: 'Show more cases',
  back: 'Cases',
} as const
