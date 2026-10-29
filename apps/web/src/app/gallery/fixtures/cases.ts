import type { CaseStatusOut, QueueItemOut, TimelineEntryOut } from '@/api/generated'

// Sample copies of the API's fixed case texts, for the gallery and the tests only. The app holds
// none of them: the form's five lines come from `GET /api/v1/cases/texts`, the sent line from
// the case routes, and the panel text from the stream's `escalation` event. These are the words
// as the API serves them for a reply-by date of Wednesday, October 28
// (apps/api/app/modules/cases/texts.py, FORM_TEXT_TEMPLATE and SENT_STATE_TEMPLATE).

export const CASE_BULLETS = [
  'HR sees your name and the words below. Managers never see a case, including your own manager.',
  'Your case is stored encrypted.',
  'HR replies by Wednesday, October 28, within 2 business days.',
  "Open Door's AI writes HR a short summary of what you send, written to be neutral, with no recommendation. Anthropic, the company that runs Open Door's AI, processes your words to write it. A person in HR reads your own words before deciding anything.",
  'If you or someone else is in danger, call 911. You can call or text 988 to reach the 988 Suicide & Crisis Lifeline, or call the Employee Assistance Program at 1-800-555-0137.',
]

/** The waiting-limit line, as `GET /cases/texts` serves it (`waitingLimit`). */
export const WAITING_LIMIT =
  'You have 5 cases waiting for HR. To add to one, contact the HR team directly.'

/** The sent line in two parts, for a person ("My cases") and for HR ("Cases"). */
export const SENT_LINE = {
  lead: 'Sent to HR. HR replies by Wednesday, October 28.',
  pointer: 'You can see its status in My cases.',
}

export const PREFILL = 'My manager keeps making comments about my age.'
export const SHORT_PREFILL = 'yes, that’s what happened'
export const SSN_WORDS = `${PREFILL} My employee number is 123-45-6789.`

/** `count` characters of plain account text. */
export function wordsOfLength(count: number): string {
  const sentence = 'My manager keeps making comments about my age in our team meetings. '
  return sentence.repeat(Math.ceil(count / sentence.length)).slice(0, count)
}

// ----- Batch B: My cases, HR's queue, and the detail (screens 11 and 12) -----
// Sample cases as the frames draw them. Every time is shown in Mountain time. "Today" is Monday,
// October 26, 2026, or Tuesday, October 27 where a frame says so.

export const CASE_ZONE = 'America/Denver'
export const TODAY = '2026-10-26'
export const TOMORROW = '2026-10-27'

export const MY_CASES: CaseStatusOut[] = [
  {
    id: 'mine-1',
    category: 'harassment_discrimination',
    status: 'new',
    sentAt: '2026-10-26T16:41:00Z',
    replyBy: '2026-10-28',
    statusChangedAt: '2026-10-26T16:41:00Z',
  },
  {
    id: 'mine-2',
    category: 'safety',
    status: 'in_review',
    sentAt: '2026-10-12T15:00:00Z',
    replyBy: '2026-10-14',
    statusChangedAt: '2026-10-13T15:00:00Z',
  },
  {
    id: 'mine-3',
    category: 'pay',
    status: 'closed',
    sentAt: '2026-09-15T15:00:00Z',
    replyBy: '2026-09-17',
    statusChangedAt: '2026-09-25T15:00:00Z',
  },
]

function queueRow(over: Partial<QueueItemOut> & Pick<QueueItemOut, 'id' | 'givenName'>) {
  return {
    category: 'other',
    personId: `person-${over.id}`,
    familyName: '',
    title: '',
    locationName: '',
    sentAt: '2026-10-26T16:41:00Z',
    replyBy: '2026-10-28',
    status: 'new',
    statusChangedAt: '2026-10-26T16:41:00Z',
    crisis: false,
    isOwn: false,
    ...over,
  } satisfies QueueItemOut
}

export const CHLOE = queueRow({
  id: 'case-chloe',
  givenName: 'Chloe',
  familyName: 'Foster',
  title: 'Shift Lead, Opening',
  locationName: 'Atlanta store',
  category: 'harassment_discrimination',
  sentAt: '2026-10-22T15:00:00Z',
  replyBy: '2026-10-26',
  statusChangedAt: '2026-10-22T15:00:00Z',
})
export const KEISHA = queueRow({
  id: 'case-keisha',
  givenName: 'Keisha',
  familyName: 'Zhang',
  title: 'Warehouse Associate',
  locationName: 'Austin warehouse',
  category: 'pay',
  sentAt: '2026-10-23T15:00:00Z',
  replyBy: '2026-10-27',
  statusChangedAt: '2026-10-23T15:00:00Z',
})
export const PRIYA_ROW = queueRow({
  id: 'case-priya',
  givenName: 'Priya',
  familyName: 'Raman',
  title: 'Visual Merchandiser',
  locationName: 'Oakland store',
  category: 'harassment_discrimination',
})
export const AALIYAH_ROW = queueRow({
  id: 'case-aaliyah',
  givenName: 'Aaliyah',
  familyName: 'Edwards',
  title: 'Cashier',
  locationName: 'Oakland store',
  category: 'safety',
  sentAt: '2026-10-19T16:12:00Z',
  replyBy: '2026-10-21',
  status: 'in_review',
  statusChangedAt: '2026-10-20T14:45:00Z',
})
export const MEGAN_ROW = queueRow({
  id: 'case-megan',
  givenName: 'Megan',
  familyName: 'Coleman',
  title: 'Shift Supervisor, Nights',
  locationName: 'Austin warehouse',
  category: 'other',
  sentAt: '2026-10-27T12:12:00Z',
  replyBy: '2026-10-29',
  statusChangedAt: '2026-10-27T12:12:00Z',
  crisis: true,
})
export const LUCIA_ROW = queueRow({
  id: 'case-lucia',
  givenName: 'Lucia',
  familyName: 'Gutierrez',
  title: 'Graphic Designer',
  locationName: 'Denver HQ',
  category: 'medical_accommodation',
  sentAt: '2026-10-05T15:00:00Z',
  replyBy: '2026-10-07',
  status: 'closed',
  statusChangedAt: '2026-10-16T15:00:00Z',
})
/** HR's own case: it appears in the queue, read-only, with no crisis fact (the API sends null). */
export const DANA_OWN_ROW = queueRow({
  id: 'case-dana',
  givenName: 'Dana',
  familyName: 'Whitfield',
  title: 'HR Business Partner',
  locationName: 'Denver HQ',
  category: 'pay',
  sentAt: '2026-10-23T20:15:00Z',
  replyBy: '2026-10-27',
  statusChangedAt: '2026-10-23T20:15:00Z',
  crisis: null,
  isOwn: true,
})

export const QUEUE_OPEN = [CHLOE, KEISHA, PRIYA_ROW, AALIYAH_ROW]
export const QUEUE_FACTS = [CHLOE, KEISHA, PRIYA_ROW, MEGAN_ROW, AALIYAH_ROW, DANA_OWN_ROW]

const DANA_ACTOR = { actorPersonId: 'dana', actorGivenName: 'Dana', actorFamilyName: 'Whitfield' }
const NO_ACTOR = { actorPersonId: null, actorGivenName: null, actorFamilyName: null }

export function timelineEntry(
  kind: TimelineEntryOut['kind'],
  occurredAt: string,
  extra: Partial<TimelineEntryOut> = {},
): TimelineEntryOut {
  const actor = kind === 'opened' || kind.startsWith('summary_') ? NO_ACTOR : DANA_ACTOR
  return { kind, occurredAt, ...actor, fromStatus: null, toStatus: null, ...extra }
}

/** What a detail frame needs to draw one case: the person, the case's facts, and its words. */
export type DemoCase = {
  id: string
  name: string
  title: string
  department: string
  location: string
  email: string
  category: QueueItemOut['category']
  status: QueueItemOut['status']
  sentAt: string
  replyBy: string
  statusChangedAt: string
  screening: string | null
  summaryText: string
  summaryWrittenAt: string
  model: string
  words: string
  entries: TimelineEntryOut[]
  isOwn?: boolean
}

export const PRIYA_CASE: DemoCase = {
  id: 'case-priya',
  name: 'Priya Raman',
  title: 'Visual Merchandiser',
  department: 'Store Operations',
  location: 'Oakland store',
  email: 'priya.raman@juniperrow.example',
  category: 'harassment_discrimination',
  status: 'new',
  sentAt: '2026-10-26T16:41:00Z',
  replyBy: '2026-10-28',
  statusChangedAt: '2026-10-26T16:41:00Z',
  screening: null,
  summaryText:
    'The person says their manager keeps making comments about their age. They don’t say when the comments started, where they were made, or whether anyone else heard them.',
  summaryWrittenAt: '2026-10-26T16:41:00Z',
  model: 'claude-opus-5-5',
  words: 'My manager keeps making comments about my age.',
  entries: [
    timelineEntry('opened', '2026-10-26T16:41:00Z'),
    timelineEntry('summary_written', '2026-10-26T16:41:00Z'),
    timelineEntry('viewed', '2026-10-26T16:52:00Z'),
  ],
}

export const AALIYAH_CASE: DemoCase = {
  id: 'case-aaliyah',
  name: 'Aaliyah Edwards',
  title: 'Cashier',
  department: 'Store Operations',
  location: 'Oakland store',
  email: 'aaliyah.edwards@juniperrow.example',
  category: 'safety',
  status: 'in_review',
  sentAt: '2026-10-19T16:12:00Z',
  replyBy: '2026-10-21',
  statusChangedAt: '2026-10-20T14:45:00Z',
  screening: null,
  summaryText:
    'The person says the top step of the stockroom ladder is cracked, and that they were told to keep using the ladder until a new one arrives. They don’t say who told them or when.',
  summaryWrittenAt: '2026-10-19T16:12:00Z',
  model: 'claude-opus-5-5',
  words:
    'The top step of the stockroom ladder is cracked. I was told to keep using it until the new ladder arrives.',
  entries: [
    timelineEntry('opened', '2026-10-19T16:12:00Z'),
    timelineEntry('summary_written', '2026-10-19T16:12:00Z'),
    timelineEntry('viewed', '2026-10-20T14:40:00Z'),
    timelineEntry('text_read', '2026-10-20T14:41:00Z'),
    timelineEntry('status_changed', '2026-10-20T14:45:00Z', {
      fromStatus: 'new',
      toStatus: 'in_review',
    }),
    timelineEntry('viewed', '2026-10-26T17:02:00Z'),
  ],
}

export const AALIYAH_CLOSED: DemoCase = {
  ...AALIYAH_CASE,
  status: 'closed',
  statusChangedAt: '2026-10-26T17:20:00Z',
  entries: [
    ...AALIYAH_CASE.entries,
    timelineEntry('status_changed', '2026-10-26T17:20:00Z', {
      fromStatus: 'in_review',
      toStatus: 'closed',
    }),
  ],
}

export const MEGAN_CASE: DemoCase = {
  id: 'case-megan',
  name: 'Megan Coleman',
  title: 'Shift Supervisor, Nights',
  department: 'Distribution',
  location: 'Austin warehouse',
  email: 'megan.coleman@juniperrow.example',
  category: 'other',
  status: 'new',
  sentAt: '2026-10-27T12:12:00Z',
  replyBy: '2026-10-29',
  statusChangedAt: '2026-10-27T12:12:00Z',
  screening: 'crisis',
  summaryText: '',
  summaryWrittenAt: '2026-10-27T12:12:00Z',
  model: 'claude-opus-5-5',
  words:
    'Nights have been really hard lately and I don’t know who else to tell. I’m not sure I can keep doing this.',
  entries: [timelineEntry('opened', '2026-10-27T12:12:00Z')],
}

export const PRIYA_PENDING: DemoCase = { ...PRIYA_CASE, entries: [PRIYA_CASE.entries[0]!] }
export const PRIYA_FAILED: DemoCase = {
  ...PRIYA_CASE,
  entries: [PRIYA_CASE.entries[0]!, timelineEntry('summary_failed', '2026-10-26T16:42:00Z')],
}

export const DANA_OWN_CASE: DemoCase = {
  id: 'case-dana',
  name: 'Dana Whitfield',
  title: 'HR Business Partner',
  department: 'Human Resources',
  location: 'Denver HQ',
  email: 'dana.whitfield@juniperrow.example',
  category: 'pay',
  status: 'new',
  sentAt: '2026-10-23T20:15:00Z',
  replyBy: '2026-10-27',
  statusChangedAt: '2026-10-23T20:15:00Z',
  screening: null,
  summaryText: '',
  summaryWrittenAt: '2026-10-23T20:15:00Z',
  model: 'claude-opus-5-5',
  words: '',
  entries: [],
  isOwn: true,
}
