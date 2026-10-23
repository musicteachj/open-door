import type {
  CancelCard,
  CheckOut,
  DecideCard,
  DrawOut,
  PersonOut,
  PtoBalanceOut,
  RequestCard,
  RequestOut,
  RuleRefOut,
  SickYearOut,
} from '@/api/generated'

// Typed fixtures for the time-off, approvals, and confirm-card sections: Priya Raman (salaried,
// Oakland, Monday to Friday) and her manager Marcus Bell, on Tuesday, October 20, 2026. Every
// figure and label is written here by hand, to match the design's frames; the browser never works
// one out. In the app the labels come from the API.

export const TODAY = '2026-10-20'
export const THIS_YEAR = 2026
export const TIME_ZONE = 'America/Los_Angeles'
/** 3:42 PM on October 20 in Oakland: 15 minutes after a card made at 3:27 PM. */
export const EXPIRES_AT = '2026-10-20T22:42:00Z'

export const PTO_RULE: RuleRefOut = {
  sectionId: '4.1',
  rule: 'pto-available',
  title: 'Paid time off',
  deepLink: '/handbook/4.1',
}
export const HOLIDAY_RULE: RuleRefOut = {
  sectionId: '4.2',
  rule: 'holidays',
  title: 'Holidays',
  deepLink: '/handbook/4.2',
}
export const SICK_RULE: RuleRefOut = {
  sectionId: 'CA-4.3',
  rule: 'sick-grant',
  title: 'Sick leave',
  deepLink: '/handbook/CA-4.3',
}

export const PRIYA: PersonOut = {
  id: 'person-priya',
  name: 'Priya Raman',
  title: 'Visual Merchandiser',
}
export const ZARA: PersonOut = {
  id: 'person-zara',
  name: 'Zara Bautista',
  title: 'Department Lead, Apparel',
}
export const MALIK: PersonOut = {
  id: 'person-malik',
  name: 'Malik Flores',
  title: 'Stock Associate',
}
export const VIKRAM: PersonOut = {
  id: 'person-vikram',
  name: 'Vikram Morales',
  title: 'Visual Merchandiser',
}
export const MARCUS = { name: 'Marcus Bell' }

// ---- Balances

export const PTO_BALANCE: PtoBalanceOut = {
  earnedMinutes: 7920,
  earnedLabel: '132 hours (16.5 days)',
  takenMinutes: 1920,
  takenLabel: '32 hours (4 days)',
  bookedMinutes: 480,
  bookedLabel: '8 hours (1 day)',
  pendingMinutes: 0,
  pendingLabel: '0 hours',
  availableMinutes: 5520,
  availableLabel: '92 hours (11.5 days)',
  ceilingMinutes: 10800,
  ceilingLabel: '180 hours (22.5 days)',
  nextEarningDate: '2026-10-31',
  nextEarningMinutes: 600,
  nextEarningLabel: '10 hours (1.25 days)',
}

/** At the 180-hour limit: 212 earned, 32 taken, 8 booked is 172 available, and earning is paused. */
export const PTO_BALANCE_CEILING: PtoBalanceOut = {
  ...PTO_BALANCE,
  earnedMinutes: 12720,
  earnedLabel: '212 hours (26.5 days)',
  availableMinutes: 10320,
  availableLabel: '172 hours (21.5 days)',
  nextEarningDate: null,
  nextEarningMinutes: 0,
  nextEarningLabel: '0 hours',
}

/** No requests at all: nothing taken or booked. */
export const PTO_BALANCE_EMPTY: PtoBalanceOut = {
  ...PTO_BALANCE,
  takenMinutes: 0,
  takenLabel: '0 hours',
  bookedMinutes: 0,
  bookedLabel: '0 hours',
  availableMinutes: 7920,
  availableLabel: '132 hours (16.5 days)',
}

export const SICK_YEAR: SickYearOut = {
  year: 2026,
  grantedMinutes: 2400,
  grantedLabel: '40 hours (5 days)',
  usedMinutes: 480,
  usedLabel: '8 hours (1 day)',
  bookedMinutes: 0,
  bookedLabel: '0 hours',
  availableMinutes: 1920,
  availableLabel: '32 hours (4 days)',
}

export const SICK_YEAR_EMPTY: SickYearOut = {
  ...SICK_YEAR,
  usedMinutes: 0,
  usedLabel: '0 hours',
  availableMinutes: 2400,
  availableLabel: '40 hours (5 days)',
}

// ---- Requests

type RequestPatch = Partial<RequestOut> & Pick<RequestOut, 'id' | 'startDate' | 'endDate'>

function request(patch: RequestPatch): RequestOut {
  return {
    person: PRIYA,
    type: 'pto',
    partialMinutes: null,
    amountMinutes: 480,
    amountLabel: '8 hours (1 day)',
    status: 'pending',
    createdAt: '2026-10-20T16:00:00Z',
    createdVia: 'ui',
    decidedBy: null,
    decidedAt: null,
    decisionNote: null,
    canceledAt: null,
    ...patch,
  }
}

export const MINE_APPROVED = request({
  id: 'req-dec-23',
  startDate: '2026-12-23',
  endDate: '2026-12-23',
  status: 'approved',
  decidedBy: MARCUS,
  decidedAt: '2026-10-05T17:00:00Z',
})
export const MINE_WAITING = request({
  id: 'req-oct-30',
  startDate: '2026-10-30',
  endDate: '2026-10-30',
  status: 'pending',
})
export const MINE_RECORDED = request({
  id: 'req-oct-22',
  startDate: '2026-10-22',
  endDate: '2026-10-22',
  type: 'sick',
  partialMinutes: 180,
  amountMinutes: 180,
  amountLabel: '3 hours',
  status: 'recorded',
})
export const MINE_CANCELED = request({
  id: 'req-oct-12',
  startDate: '2026-10-12',
  endDate: '2026-10-12',
  status: 'canceled',
  canceledAt: '2026-10-08T17:00:00Z',
})
export const MINE_DENIED = request({
  id: 'req-aug-28',
  startDate: '2026-08-28',
  endDate: '2026-08-28',
  status: 'denied',
  decidedBy: MARCUS,
  decidedAt: '2026-08-20T17:00:00Z',
  decisionNote:
    'We’re short-staffed for the back-to-school sale that week. Could you pick another Friday?',
})

/** Zara's waiting request, as Marcus sees it: 62 hours available, Vikram off on the 10th. */
export const ZARA_WAITING = request({
  id: 'req-zara-nov-9',
  person: ZARA,
  startDate: '2026-11-09',
  endDate: '2026-11-10',
  amountMinutes: 960,
  amountLabel: '16 hours (2 days)',
  status: 'pending',
  createdAt: '2026-10-17T18:00:00Z',
  availableAfterMinutes: 3720,
  availableAfterLabel: '62 hours (7.75 days)',
  coverage: [
    {
      person: { id: VIKRAM.id, name: VIKRAM.name },
      days: [{ date: '2026-11-10', type: 'pto', partialMinutes: null }],
    },
  ],
})
export const PRIYA_WAITING = request({
  id: 'req-priya-oct-30',
  person: PRIYA,
  startDate: '2026-10-30',
  endDate: '2026-10-30',
  status: 'pending',
  createdAt: '2026-10-20T16:00:00Z',
  availableAfterMinutes: 5040,
  availableAfterLabel: '84 hours (10.5 days)',
  coverage: [],
})

export const TEAM_SICK = request({
  id: 'req-malik-oct-22',
  person: MALIK,
  type: 'sick',
  startDate: '2026-10-22',
  endDate: '2026-10-22',
  partialMinutes: 180,
  amountMinutes: 180,
  amountLabel: '3 hours',
  status: 'recorded',
})
export const TEAM_APPROVED = request({
  id: 'req-vikram-nov-10',
  person: VIKRAM,
  startDate: '2026-11-10',
  endDate: '2026-11-10',
  status: 'approved',
  decidedBy: MARCUS,
  decidedAt: '2026-10-05T17:00:00Z',
})
export const TEAM_DENIED = request({
  id: 'req-priya-aug-28',
  person: PRIYA,
  startDate: '2026-08-28',
  endDate: '2026-08-28',
  status: 'denied',
  decidedBy: MARCUS,
  decidedAt: '2026-08-20T17:00:00Z',
  decisionNote:
    'We’re short-staffed for the back-to-school sale that week. Could you pick another Friday?',
})

// ---- Preview data, in the check route's shape

function draw(partial: Partial<DrawOut>): DrawOut {
  return {
    year: null,
    amountMinutes: 480,
    amountLabel: '8 hours (1 day)',
    availableBeforeMinutes: 5520,
    availableBeforeLabel: '92 hours (11.5 days)',
    availableAfterMinutes: 5040,
    availableAfterLabel: '84 hours (10.5 days)',
    ...partial,
  }
}

function check(partial: Partial<CheckOut>): CheckOut {
  return {
    ok: true,
    problems: [],
    warnings: [],
    countedDays: [],
    skippedDays: [],
    overlappingDays: [],
    amountMinutes: 480,
    amountLabel: '8 hours (1 day)',
    draws: [draw({})],
    rules: [PTO_RULE],
    ...partial,
  }
}

const weekdays = (...days: string[]) => days
const NOT_SCHEDULED = 'not scheduled'

export const CHECK_ONE_DAY = check({ countedDays: ['2026-10-30'] })
export const CHECK_WEEKEND = check({
  countedDays: ['2026-10-30', '2026-11-02'],
  skippedDays: [
    { day: '2026-10-31', reason: NOT_SCHEDULED },
    { day: '2026-11-01', reason: NOT_SCHEDULED },
  ],
  amountMinutes: 960,
  amountLabel: '16 hours (2 days)',
  draws: [
    draw({
      amountMinutes: 960,
      amountLabel: '16 hours (2 days)',
      availableAfterMinutes: 4560,
      availableAfterLabel: '76 hours (9.5 days)',
    }),
  ],
})
export const CHECK_HOLIDAY = check({
  countedDays: ['2026-11-25', '2026-11-27'],
  skippedDays: [{ day: '2026-11-26', reason: 'Thanksgiving' }],
  amountMinutes: 960,
  amountLabel: '16 hours (2 days)',
  draws: [
    draw({
      amountMinutes: 960,
      amountLabel: '16 hours (2 days)',
      availableAfterMinutes: 4560,
      availableAfterLabel: '76 hours (9.5 days)',
    }),
  ],
  rules: [PTO_RULE, HOLIDAY_RULE],
})
export const CHECK_SICK_HOURS = check({
  countedDays: ['2026-10-22'],
  amountMinutes: 180,
  amountLabel: '3 hours',
  draws: [
    draw({
      year: 2026,
      amountMinutes: 180,
      amountLabel: '3 hours',
      availableBeforeMinutes: 1920,
      availableBeforeLabel: '32 hours (4 days)',
      availableAfterMinutes: 1740,
      availableAfterLabel: '29 hours',
    }),
  ],
  rules: [SICK_RULE],
})
export const CHECK_SHORT_NOTICE = check({
  warnings: ['short-notice'],
  countedDays: weekdays('2026-11-02', '2026-11-03', '2026-11-04', '2026-11-05'),
  amountMinutes: 1920,
  amountLabel: '32 hours (4 days)',
  draws: [
    draw({
      amountMinutes: 1920,
      amountLabel: '32 hours (4 days)',
      availableAfterMinutes: 3600,
      availableAfterLabel: '60 hours (7.5 days)',
    }),
  ],
})
/** Three weeks of weekdays: the counted days run together, and the weekends fold into one line. */
const THREE_WEEKS = weekdays(
  '2026-11-30',
  '2026-12-01',
  '2026-12-02',
  '2026-12-03',
  '2026-12-04',
  '2026-12-07',
  '2026-12-08',
  '2026-12-09',
  '2026-12-10',
  '2026-12-11',
  '2026-12-14',
  '2026-12-15',
  '2026-12-16',
  '2026-12-17',
  '2026-12-18',
)
const WEEKENDS = ['2026-12-05', '2026-12-06', '2026-12-12', '2026-12-13'].map((day) => ({
  day,
  reason: NOT_SCHEDULED,
}))
export const CHECK_NOT_ENOUGH = check({
  ok: false,
  problems: [{ code: 'not-enough', text: 'That is more PTO than you have available.' }],
  countedDays: THREE_WEEKS,
  skippedDays: WEEKENDS,
  amountMinutes: 7200,
  amountLabel: '120 hours (15 days)',
  draws: [
    draw({
      amountMinutes: 7200,
      amountLabel: '120 hours (15 days)',
      availableAfterMinutes: -1680,
      availableAfterLabel: '-28 hours (-3.5 days)',
    }),
  ],
})
export const CHECK_LONG_RUNS = check({
  countedDays: THREE_WEEKS.slice(0, 10),
  skippedDays: WEEKENDS.slice(0, 2),
  amountMinutes: 4800,
  amountLabel: '80 hours (10 days)',
  draws: [
    draw({
      amountMinutes: 4800,
      amountLabel: '80 hours (10 days)',
      availableAfterMinutes: 720,
      availableAfterLabel: '12 hours (1.5 days)',
    }),
  ],
})
export const CHECK_OVERLAP = check({
  ok: false,
  problems: [{ code: 'overlaps', text: 'You already have time off on those days.' }],
  countedDays: ['2026-12-23'],
  overlappingDays: ['2026-12-23'],
})
/**
 * Sick time from Wednesday, December 30 to Monday, January 4, as the engine answers it for Priya
 * (Oakland, Monday to Friday, 40 hours granted each year). Friday, January 1 is New Year's Day, a
 * company holiday, and the weekend is off her schedule, so three days count.
 *   2026: Dec 30 and 31 are 2 days x 8 hours = 16 hours. 32 available before, 32 - 16 = 16 after.
 *   2027: Jan 4 is 1 day x 8 hours = 8 hours. 40 available before, 40 - 8 = 32 after.
 *   Total: 16 + 8 = 24 hours (3 days).
 */
export const CHECK_CROSS_YEAR_SICK = check({
  countedDays: ['2026-12-30', '2026-12-31', '2027-01-04'],
  skippedDays: [
    { day: '2027-01-01', reason: "New Year's Day" },
    { day: '2027-01-02', reason: NOT_SCHEDULED },
    { day: '2027-01-03', reason: NOT_SCHEDULED },
  ],
  amountMinutes: 1440,
  amountLabel: '24 hours (3 days)',
  draws: [
    draw({
      year: 2026,
      amountMinutes: 960,
      amountLabel: '16 hours (2 days)',
      availableBeforeMinutes: 1920,
      availableBeforeLabel: '32 hours (4 days)',
      availableAfterMinutes: 960,
      availableAfterLabel: '16 hours (2 days)',
    }),
    draw({
      year: 2027,
      amountMinutes: 480,
      amountLabel: '8 hours (1 day)',
      availableBeforeMinutes: 2400,
      availableBeforeLabel: '40 hours (5 days)',
      availableAfterMinutes: 1920,
      availableAfterLabel: '32 hours (4 days)',
    }),
  ],
  rules: [SICK_RULE],
})
export const CHECK_NOTHING_COUNTED = check({
  ok: false,
  problems: [{ code: 'no-scheduled-days', text: 'None of those days are on your schedule.' }],
  skippedDays: [
    { day: '2026-10-31', reason: NOT_SCHEDULED },
    { day: '2026-11-01', reason: NOT_SCHEDULED },
  ],
  amountMinutes: null,
  amountLabel: null,
  draws: [],
})

// ---- Confirm cards

function requestCard(partial: Partial<RequestCard>): RequestCard {
  const preview = CHECK_ONE_DAY
  return {
    kind: 'request',
    type: 'pto',
    startDate: '2026-10-30',
    endDate: '2026-10-30',
    partialMinutes: null,
    countedDays: preview.countedDays,
    skippedDays: preview.skippedDays,
    amountMinutes: 480,
    amountLabel: '8 hours (1 day)',
    draws: preview.draws,
    warnings: [],
    approver: MARCUS,
    rules: [PTO_RULE],
    ...partial,
  }
}

export const CARD_BOOK = requestCard({})
export const CARD_HOLIDAY = requestCard({
  startDate: '2026-11-25',
  endDate: '2026-11-27',
  countedDays: CHECK_HOLIDAY.countedDays,
  skippedDays: CHECK_HOLIDAY.skippedDays,
  amountMinutes: 960,
  amountLabel: '16 hours (2 days)',
  draws: CHECK_HOLIDAY.draws,
  rules: [PTO_RULE, HOLIDAY_RULE],
})
export const CARD_SICK = requestCard({
  type: 'sick',
  startDate: '2026-10-22',
  endDate: '2026-10-22',
  partialMinutes: 180,
  countedDays: CHECK_SICK_HOURS.countedDays,
  amountMinutes: 180,
  amountLabel: '3 hours',
  draws: CHECK_SICK_HOURS.draws,
  approver: null,
  rules: [SICK_RULE],
})
export const CARD_SHORT_NOTICE = requestCard({
  startDate: '2026-11-02',
  endDate: '2026-11-05',
  countedDays: CHECK_SHORT_NOTICE.countedDays,
  amountMinutes: 1920,
  amountLabel: '32 hours (4 days)',
  draws: CHECK_SHORT_NOTICE.draws,
  warnings: ['short-notice'],
})
export const CARD_CROSS_YEAR_SICK = requestCard({
  type: 'sick',
  startDate: '2026-12-30',
  endDate: '2027-01-04',
  countedDays: CHECK_CROSS_YEAR_SICK.countedDays,
  skippedDays: CHECK_CROSS_YEAR_SICK.skippedDays,
  amountMinutes: 1440,
  amountLabel: '24 hours (3 days)',
  draws: CHECK_CROSS_YEAR_SICK.draws,
  approver: null,
  rules: [SICK_RULE],
})

function decideCard(partial: Partial<DecideCard>): DecideCard {
  return {
    kind: 'decide',
    requester: ZARA,
    type: 'pto',
    startDate: '2026-11-09',
    endDate: '2026-11-10',
    partialMinutes: null,
    amountMinutes: 960,
    amountLabel: '16 hours (2 days)',
    availableAfterMinutes: 3720,
    availableAfterLabel: '62 hours (7.75 days)',
    coverage: ZARA_WAITING.coverage ?? [],
    decision: 'deny',
    rules: [PTO_RULE],
    ...partial,
  }
}

export const CARD_DENY = decideCard({})
export const CARD_APPROVE = decideCard({
  requester: PRIYA,
  startDate: '2026-10-30',
  endDate: '2026-10-30',
  amountMinutes: 480,
  amountLabel: '8 hours (1 day)',
  availableAfterMinutes: 5040,
  availableAfterLabel: '84 hours (10.5 days)',
  coverage: [],
  decision: 'approve',
})

export const CARD_CANCEL: CancelCard = {
  kind: 'cancel',
  type: 'pto',
  startDate: '2026-12-23',
  endDate: '2026-12-23',
  partialMinutes: null,
  status: 'approved',
  amountMinutes: 480,
  amountLabel: '8 hours (1 day)',
  returnsMinutes: 480,
  returnsLabel: '8 hours (1 day)',
  availableAfterMinutes: 6000,
  availableAfterLabel: '100 hours (12.5 days)',
  rules: [PTO_RULE],
}
export const CARD_CANCEL_SICK: CancelCard = {
  ...CARD_CANCEL,
  type: 'sick',
  startDate: '2026-10-22',
  endDate: '2026-10-22',
  status: 'recorded',
  amountMinutes: 180,
  amountLabel: '3 hours',
  returnsMinutes: null,
  returnsLabel: null,
  availableAfterMinutes: null,
  availableAfterLabel: null,
  rules: [SICK_RULE],
}
