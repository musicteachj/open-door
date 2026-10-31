import type {
  CitationOut,
  GuardOut,
  Inline,
  ParagraphPassage,
  PassageView,
  SectionOut,
  SectionSummary,
  ToolCallOut,
} from '@/api/generated'
import { numberBySection } from '@/components/assistant/sources'

// Sample data for the conversation gallery (conversation-sections.tsx), and nothing else: the app
// never imports this file. The words are the design's own (docs/design/screens/07-conversation/
// notes.md, "Sample answers", and the screenshots), and the fixed texts are copied verbatim from
// apps/api/app/ai/fixed_texts.py and apps/api/app/modules/assistant/routes.py, so the gallery shows
// what a person would see. The app itself gets those texts only from the stream, never from a copy.
//
// The sick leave and overtime figures match the sourced handbook sections they cite (CA-4.3 and
// CA-3.2 give California's 40 hours and its daily overtime). The design's first sentence said
// "instead of the company's 3 days", but §4.3 gives every employee 40 hours (5 days), so the sample
// says what CA-4.3 actually adds: 40 hours or 5 workdays, whichever is more.

// ----- Fixed texts, verbatim -----

export const CRISIS_TEXT = `I'm an AI assistant, and what you wrote sounds serious, so I want to make sure you can reach a person right now.

- If you or someone else is in immediate danger, call 911.
- Call or text 988 to reach the 988 Suicide & Crisis Lifeline, or chat at chat.988lifeline.org. It's free, confidential, and available 24/7.
- The Juniper Row Employee Assistance Program (EAP) offers free, confidential counseling, 24 hours a day: 1-800-555-0137.
- You can also talk to someone on the HR team. Their contact details are below.

You don't have to go through this alone.`

export const SENSITIVE_TEXT =
  'This sounds like something a person on the HR team should help with. You can open a ' +
  "confidential case below. Only the HR team can open it in Open Door, never your manager, and it's " +
  'stored encrypted. HR replies within 2 business days. Their contact details are below.'

export const UNAVAILABLE_TEXT =
  "I'm an AI assistant, and I can't answer right now. Please try again in a moment. If you or " +
  'someone else is in danger, call 911, or call or text 988 to reach the 988 Suicide & Crisis ' +
  "Lifeline. For anything else that can't wait, the HR team can help directly. Their contact " +
  'details are below.'

export const BUDGET_SANDBOX_TEXT =
  'This demo sandbox has reached its limit for the assistant. A new sandbox starts fresh. ' +
  'If you or someone else is in danger, call 911, or call or text 988 to reach the 988 ' +
  'Suicide & Crisis Lifeline.'

export const BUDGET_DAILY_TEXT =
  "The demo's daily limit for the assistant has been reached. Please try again tomorrow. " +
  'If you or someone else is in danger, call 911, or call or text 988 to reach the 988 ' +
  'Suicide & Crisis Lifeline.'

/** ERROR_TEXTS["internal"]: the nearest in meaning to the design's "Something went wrong partway". */
export const ERROR_INTERNAL_TEXT =
  "Something went wrong on our side, and I couldn't finish that. Please try again, or ask the " +
  'HR team.'

/** The 409 from the conversation route, when a question is sent while an answer is streaming. */
export const STILL_ANSWERING_TEXT = "I'm still answering your last question."

/** The 422 from the conversation route, when a question holds a Social Security or card number. */
export const PERSONAL_DATA_TEXT =
  "That looks like a Social Security or card number. Please take it out; I can't take those."

// ----- Sample people -----

/** Dana Whitfield, with the title and location the conversation API will send (Stage 6). */
export const DANA = {
  name: 'Dana Whitfield',
  workEmail: 'dana.whitfield@juniperrow.example',
  jobTitle: 'HR Business Partner',
  locationName: 'Denver HQ',
}

// ----- Passages, and the citations built from them -----

type PassageRef = Pick<
  CitationOut,
  'sectionId' | 'passageId' | 'title' | 'groupName' | 'audienceLabel' | 'lastUpdated' | 'citedText'
>

const CALIFORNIA = 'California addendum'
// A company section's group is its chapter's name, from handbook/handbook.yaml, as the API sends it.
const TIME_OFF = 'Time off'
const HOURS_AND_PAY = 'Hours and pay'
const WORKING_HERE = 'Working here'
const PRIVACY = 'Privacy and confidential cases'

const CA_43_P1: PassageRef = {
  sectionId: 'CA-4.3',
  passageId: 'CA-4.3~p1',
  title: 'Sick leave',
  groupName: CALIFORNIA,
  audienceLabel: 'California employees',
  lastUpdated: '2026-09-12',
  citedText:
    'California employees receive 40 hours (5 days) of paid sick leave at the start of each calendar year.',
}
const CA_43_P2: PassageRef = {
  ...CA_43_P1,
  passageId: 'CA-4.3~p2',
  citedText:
    'You can use sick leave for your own illness, injury, or preventive care, or to care for a family member.',
}
const S_43_P3: PassageRef = {
  sectionId: '4.3',
  passageId: '4.3~p3',
  title: 'Sick leave',
  groupName: TIME_OFF,
  audienceLabel: 'Everyone',
  lastUpdated: '2026-10-13',
  citedText: 'Tell your manager as early as you can when you will be out.',
}
const CA_32_P1: PassageRef = {
  sectionId: 'CA-3.2',
  passageId: 'CA-3.2~p1',
  title: 'Overtime',
  groupName: CALIFORNIA,
  audienceLabel: 'Hourly staff in California',
  lastUpdated: '2026-10-07',
  citedText: 'California counts overtime by the day as well as by the week.',
}
const S_32_P1: PassageRef = {
  sectionId: '3.2',
  passageId: '3.2~p1',
  title: 'Overtime',
  groupName: HOURS_AND_PAY,
  audienceLabel: 'Hourly staff',
  lastUpdated: '2026-10-07',
  citedText:
    'Non-exempt employees must be paid overtime at time and one-half their regular rate for hours worked over 40 in a workweek.',
}
const S_71_P1: PassageRef = {
  sectionId: '7.1',
  passageId: '7.1~p1',
  title: 'Your personal information',
  groupName: PRIVACY,
  audienceLabel: 'Everyone',
  lastUpdated: '2026-10-07',
  citedText: 'Only you and HR can see your home address.',
}
const S_23_P1: PassageRef = {
  sectionId: '2.3',
  passageId: '2.3~p1',
  title: 'Raising a concern',
  groupName: WORKING_HERE,
  audienceLabel: 'Everyone',
  lastUpdated: '2026-10-07',
  citedText: 'You can raise a concern with HR directly.',
}
const S_42_P1: PassageRef = {
  sectionId: '4.2',
  passageId: '4.2~p1',
  title: 'Holidays',
  groupName: TIME_OFF,
  audienceLabel: 'Everyone',
  lastUpdated: '2026-10-13',
  citedText: 'Every Juniper Row location closes on six holidays.',
}

/**
 * Citations as the API sends them (each distinct passage gets the next marker number, a passage
 * cited twice repeats its number, and `offsetUtf16` is where the marker goes in `text`), then
 * numbered by section the way the chat store and the conversation query do it, because the
 * components take numbered citations. Each cite is the end of a phrase in `text` and the passage
 * it supports, so the offsets can't drift from the words.
 */
function cited(text: string, ...cites: [after: string, passage: PassageRef][]): CitationOut[] {
  const numbers = new Map<string, number>()
  const raw = cites.map(([after, passage]) => {
    const at = text.indexOf(after)
    if (at === -1) throw new Error(`"${after}" is not in the sample text.`)
    let marker = numbers.get(passage.passageId)
    if (marker === undefined) {
      marker = numbers.size + 1
      numbers.set(passage.passageId, marker)
    }
    return {
      ...passage,
      marker,
      offsetUtf16: at + after.length,
      deepLink: `/handbook/${passage.sectionId}?passage=${passage.passageId}`,
    }
  })
  return numberBySection(raw)
}

// ----- Turns: a question, the answer, and what "Show your work" lists -----

export type SampleTurn = {
  question: string
  text: string
  citations: CitationOut[]
  guard: GuardOut
  toolCalls: ToolCallOut[]
  sections: SectionOut[]
}

const tool = (name: string, inputSummary: string): ToolCallOut => ({
  name,
  inputSummary,
  ok: true,
  durationMs: 120,
})
const search = (query: string) => tool('search_handbook', `query='${query}'`)
const ORDINARY: GuardOut = { category: 'ordinary' }

const SICK_TEXT = [
  'You get 5 days of paid sick leave a year, which is 40 hours. Because you work in California, the California addendum applies, and it gives you 40 hours or 5 of your workdays, whichever is more.',
  'The full 40 hours are available at the start of each calendar year. Unused sick leave doesn’t carry over, and it isn’t paid out when you leave.',
  'You can use it for your own illness, injury, or preventive care, or to care for a family member. You don’t need to give a reason beyond saying it’s sick leave. Tell your manager before your shift starts, or as soon as you can.',
].join('\n\n')

/** Priya's sick leave question: four markers over two sections, and two sections not cited. */
export const SICK_TURN: SampleTurn = {
  question: 'How many sick days do I get?',
  text: SICK_TEXT,
  citations: cited(
    SICK_TEXT,
    ['5 of your workdays, whichever is more.', CA_43_P1],
    ['isn’t paid out when you leave.', CA_43_P1],
    ['reason beyond saying it’s sick leave.', CA_43_P2],
    ['or as soon as you can.', S_43_P3],
  ),
  guard: ORDINARY,
  toolCalls: [tool('get_my_profile', ''), search('sick leave'), search('California sick leave')],
  sections: [
    {
      sectionId: 'CA-4.3',
      passageIds: ['CA-4.3~p1', 'CA-4.3~p2'],
      title: 'Sick leave',
      groupName: CALIFORNIA,
    },
    { sectionId: '4.3', passageIds: ['4.3~p3'], title: 'Sick leave', groupName: TIME_OFF },
    {
      sectionId: 'CO-4.3',
      passageIds: ['CO-4.3~p1'],
      title: 'Sick leave',
      groupName: 'Colorado addendum',
    },
    { sectionId: '4.1', passageIds: ['4.1~p1'], title: 'Paid time off', groupName: TIME_OFF },
  ],
}

/** The first words of that answer, as they stream: the first marker is in, and the caret waits. */
export const SICK_STREAMING_TEXT =
  'You get 5 days of paid sick leave a year, which is 40 hours. Because you work in California, the California '
export const SICK_STOPPED_TEXT =
  'You get 5 days of paid sick leave a year, which is 40 hours. Because you work in California, the California addendum sets your amount'
export const SICK_ERROR_TEXT =
  'You get 5 days of paid sick leave a year, which is 40 hours. Because you work in California, the California'
const firstMarker = (text: string) => cited(text, ['which is 40 hours.', CA_43_P1])
export const SICK_STREAMING_CITATIONS = firstMarker(SICK_STREAMING_TEXT)
export const SICK_STOPPED_CITATIONS = firstMarker(SICK_STOPPED_TEXT)
export const SICK_ERROR_CITATIONS = firstMarker(SICK_ERROR_TEXT)

const OVERTIME_TEXT = [
  'Here’s the California policy. Hourly staff in California are paid overtime for hours over 8 in a workday or 40 in a workweek, and double time for hours over 12 in a workday.',
  'It doesn’t apply to you, because you work at the Austin warehouse in Texas. For you, the company policy applies: overtime is 1.5 times your regular rate for hours over 40 in a workweek.',
].join('\n\n')

/** Mateo's question, about another state's policy. */
export const OTHER_STATE_TURN: SampleTurn = {
  question: 'What’s the overtime rule in California?',
  text: OVERTIME_TEXT,
  citations: cited(
    OVERTIME_TEXT,
    ['over 12 in a workday.', CA_32_P1],
    ['over 40 in a workweek.', S_32_P1],
  ),
  guard: ORDINARY,
  toolCalls: [tool('get_my_profile', ''), search('overtime California')],
  sections: [
    { sectionId: 'CA-3.2', passageIds: ['CA-3.2~p1'], title: 'Overtime', groupName: CALIFORNIA },
    { sectionId: '3.2', passageIds: ['3.2~p1'], title: 'Overtime', groupName: HOURS_AND_PAY },
  ],
}

const NOT_FOUND_TEXT = [
  'I couldn’t find that in the handbook. I searched for tuition reimbursement and education benefits, and no section covers them.',
  'The HR team can tell you whether Juniper Row offers anything like this.',
].join('\n\n')

/** A question the handbook doesn't answer: no citations, and the HR contacts under it. */
export const NOT_FOUND_TURN: SampleTurn = {
  question: 'Is there a tuition reimbursement program?',
  text: NOT_FOUND_TEXT,
  citations: [],
  guard: ORDINARY,
  toolCalls: [search('tuition reimbursement'), search('education benefits')],
  sections: [],
}

const REFUSAL_TEXT = [
  'I can’t share another employee’s home address. Home addresses are private, and only the employee and HR can see them.',
  'If you’d like to send Elena a card, you could give it to her at work or ask HR to pass it along. Her work email and location are in the [Directory](/directory/).',
].join('\n\n')

/** A request for another person's private details, answered as a refusal. */
export const REFUSAL_TURN: SampleTurn = {
  question: 'What’s Elena Baker’s home address? I want to mail her a card.',
  text: REFUSAL_TEXT,
  citations: cited(REFUSAL_TEXT, ['and HR can see them.', S_71_P1]),
  guard: ORDINARY,
  toolCalls: [search('home address privacy')],
  sections: [
    {
      sectionId: '7.1',
      passageIds: ['7.1~p1'],
      title: 'Your personal information',
      groupName: PRIVACY,
    },
  ],
}

const SENSITIVE_ANSWER_TEXT =
  'I’m sorry you’re dealing with this. I can’t judge what happened or advise you on it. The handbook says you can raise a concern with HR directly, and the HR team handles it confidentially.'

/**
 * A sensitive question. The assistant answers, with a note not to counsel or judge (Build
 * decisions), and the fixed panel follows. The safety check reads "Routed to HR guidance".
 */
export const SENSITIVE_TURN: SampleTurn = {
  question: 'My manager keeps commenting on how I look, and it’s making me uncomfortable.',
  text: SENSITIVE_ANSWER_TEXT,
  citations: cited(SENSITIVE_ANSWER_TEXT, ['handles it confidentially.', S_23_P1]),
  guard: { category: 'sensitive', kind: 'harassment' },
  toolCalls: [search('raise a concern')],
  sections: [
    {
      sectionId: '2.3',
      passageIds: ['2.3~p1'],
      title: 'Raising a concern',
      groupName: WORKING_HERE,
    },
    {
      sectionId: '7.2',
      passageIds: ['7.2~p1'],
      title: 'How confidential HR cases work',
      groupName: PRIVACY,
    },
  ],
}

export const CRISIS_QUESTION =
  'Everything feels hopeless lately, and I don’t know if I can keep going.'

const NO_REASON_TEXT =
  'No. You don’t need to give a reason beyond saying the time is sick leave. Tell your manager before your shift starts, or as soon as you can.'
const HOLIDAYS_TEXT =
  'Juniper Row observes six paid holidays: New Year’s Day, Memorial Day, Independence Day, Labor Day, Thanksgiving Day, and Christmas Day.'

/** The two turns of the long conversation. */
export const LONG_TURNS: SampleTurn[] = [
  {
    question: 'Do I have to tell my manager why?',
    text: NO_REASON_TEXT,
    citations: cited(
      NO_REASON_TEXT,
      ['saying the time is sick leave.', CA_43_P2],
      ['or as soon as you can.', S_43_P3],
    ),
    guard: ORDINARY,
    toolCalls: [tool('get_my_profile', ''), search('sick leave reason manager')],
    sections: [
      {
        sectionId: 'CA-4.3',
        passageIds: ['CA-4.3~p2'],
        title: 'Sick leave',
        groupName: CALIFORNIA,
      },
      { sectionId: '4.3', passageIds: ['4.3~p3'], title: 'Sick leave', groupName: TIME_OFF },
    ],
  },
  {
    question: 'What holidays do we have this year?',
    text: HOLIDAYS_TEXT,
    citations: cited(HOLIDAYS_TEXT, ['and Christmas Day.', S_42_P1]),
    guard: ORDINARY,
    toolCalls: [search('company holidays')],
    sections: [
      { sectionId: '4.2', passageIds: ['4.2~p1'], title: 'Holidays', groupName: TIME_OFF },
    ],
  },
]

/** What Priya types before the length hint shows: 1,962 characters, near the 2,000 limit. */
export const LENGTH_HINT_DRAFT =
  'I’m planning time off around my sister’s wedding in March and want to get the details right before I submit anything. ' +
  'The wedding is in Sacramento on Saturday, March 13, and I’d like to take Thursday the 11th through Tuesday the 16th so I have time to travel and help with setup. ' +
  'I have 11.5 days of PTO right now and one request pending for a long weekend in February, so I want to be sure the new request will not collide with it. ' +
  'Before I send anything, I would like to know whether the days I’m asking for come out of my PTO balance, whether any of them count as sick leave or a holiday, ' +
  'and whether my manager has to approve the request before I book my flights. I would also like to know how far ahead I need to ask, ' +
  'whether weekends in the middle of the trip count against my balance, and what happens if the dates change after I have already submitted the request. ' +
  'My manager is traveling the week before, so I would like to send the request early, and I’d like to confirm that I can still change it later without starting over. ' +
  'If I need to split the trip into two requests, please tell me how that works, and whether the second one needs its own approval or follows the first. ' +
  'Finally, I would like to double check that nothing in the handbook limits how many consecutive days I can take at once, since this would be my longest trip this year and I do not want any surprises when I submit it. ' +
  'Thank you for your help with all of this, and please let me know if there is anything else I should have ready before I send the request to my manager for approval on Monday morning, including any forms, dates, or notes about coverage for my work while I am away from the store. ' +
  'I can also send my coverage notes to a teammate ahead of time, if that helps, and I am happy to move one of the days if the schedule is tight. ' +
  'I would rather ask now than find out later, so please walk me through each step in the order I should take them, starting with the first.'

export const PERSONAL_DATA_DRAFT =
  'Can you check my last paycheck? My Social Security number is 123-45-6789.'

// ----- The source panel's passages -----

const run = (text: string, extra: Partial<Inline> = {}): Inline => ({
  text,
  bold: false,
  italic: false,
  linkSectionId: null,
  ...extra,
})
const para = (id: string, text: string): ParagraphPassage => ({
  type: 'passage',
  id,
  kind: 'paragraph',
  inlines: [run(text)],
})

const EVERYONE = { states: [], employmentTypes: [], locations: [] }

const CA_43: SectionSummary = {
  id: 'CA-4.3',
  title: 'Sick leave',
  kind: 'addendum',
  chapter: null,
  addendumState: 'CA',
  groupName: CALIFORNIA,
  audience: { ...EVERYONE, states: ['CA'] },
  audienceLabel: 'California employees',
  appliesToMe: true,
  lastUpdated: '2026-09-12',
}
const S_43: SectionSummary = {
  id: '4.3',
  title: 'Sick leave',
  kind: 'company',
  chapter: 4,
  addendumState: null,
  groupName: TIME_OFF,
  audience: EVERYONE,
  audienceLabel: 'Everyone',
  appliesToMe: true,
  lastUpdated: '2026-10-13',
}

const CA_P1 = para(
  'p1',
  'California employees receive 40 hours (5 days) of paid sick leave at the start of each calendar year. Unused sick leave does not carry over, and it is not paid out when employment ends.',
)
const CA_P2 = para(
  'p2',
  'You can use sick leave for your own illness, injury, or preventive care, or to care for a family member. You do not need to give a reason beyond that the time is sick leave.',
)
const CA_P3 = para(
  'p3',
  'If you know about the need ahead of time, such as a scheduled appointment, tell your manager in advance. Otherwise, tell them as soon as you can.',
)

/** What the passage route returns for each passage the sick leave answer cites. */
export const SICK_PASSAGE_VIEWS: Record<string, PassageView> = {
  'CA-4.3~p1': { section: CA_43, previous: null, passage: CA_P1, next: CA_P2 },
  'CA-4.3~p2': { section: CA_43, previous: CA_P1, passage: CA_P2, next: CA_P3 },
  '4.3~p3': {
    section: S_43,
    previous: null,
    passage: para(
      'p3',
      'Tell your manager as early as you can when you will be out, and record the time in Open Door.',
    ),
    next: null,
  },
}
