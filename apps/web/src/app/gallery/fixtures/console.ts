import type { ConsoleMetricsOut, ConsoleTurnOut } from '@/api/generated'

// The AI Ops console's sample day (screen 13): Monday, October 26, 2026, in Mountain time, in a
// fresh sandbox right after the tour. The rows and metrics have the API's own shape, so Stage 6
// only adds the queries. `inputTokens` is the plain input, as the API sends it: the trace adds the
// cache reads back ("Input 12,400 (10,200 from cache)"); cache writes are their own row.

export const CONSOLE_ZONE = 'America/Denver'

const TITLES: Record<string, string> = {
  '4.1': 'Paid time off',
  '4.3': 'Sick leave',
  '5.2': 'Parental leave',
  'CA-4.3': 'Sick leave (California)',
}

/** A handbook section's title, or undefined for one the lookup doesn't hold. */
export const sectionTitle = (id: string): string | undefined => TITLES[id]

const BASE: ConsoleTurnOut = {
  id: 'turn-0',
  occurredOn: '2026-10-26',
  occurredAt: '2026-10-26T16:31:00Z',
  flagged: false,
  abandoned: false,
  askerRole: 'employee',
  askerLocation: 'Oakland, CA',
  outcome: 'answered',
  refusalCategory: null,
  guardCategory: 'ordinary',
  injectionSuspected: false,
  tools: [],
  sectionsRetrieved: [],
  sectionsCited: [],
  cardAction: null,
  servedBy: ['claude-opus-5-5'],
  fallback: false,
  effort: 'low',
  promptVersion: '2026-11.2',
  toolsetVersion: '2026-11.2',
  inputTokens: 2000,
  outputTokens: 400,
  cacheReadTokens: 8000,
  cacheWriteTokens: 0,
  costUsd: 0.02,
  guardMs: 640,
  firstTextMs: 1500,
  totalMs: 3200,
}

/** A console row: the plain defaults, with whatever a test or state changes. */
export function turn(overrides: Partial<ConsoleTurnOut> = {}): ConsoleTurnOut {
  return { ...BASE, ...overrides }
}

const ok = (name: string, durationMs: number) => ({ name, ok: true, durationMs })

// The eight timed rows, newest first, as the API orders them (the flagged row follows).
export const T_1038_INJECTION = turn({
  id: 'turn-1038a',
  occurredAt: '2026-10-26T16:38:00Z',
  injectionSuspected: true,
  inputTokens: 1780,
  cacheReadTokens: 5120,
  outputTokens: 120,
  costUsd: 0.011,
  guardMs: 980,
  firstTextMs: 1100,
  totalMs: 2000,
})
export const T_1038_PEOPLE = turn({
  id: 'turn-1038b',
  occurredAt: '2026-10-26T16:38:30Z',
  tools: [ok('find_people', 60)],
  inputTokens: 1800,
  cacheReadTokens: 8000,
  outputTokens: 300,
  costUsd: 0.022,
  firstTextMs: 1700,
  totalMs: 3400,
})
export const T_1036 = turn({
  id: 'turn-1036',
  occurredAt: '2026-10-26T16:36:00Z',
  askerRole: 'manager',
  tools: [ok('list_time_off_requests', 95)],
  inputTokens: 1500,
  cacheReadTokens: 7100,
  outputTokens: 260,
  costUsd: 0.018,
  guardMs: 610,
  firstTextMs: 1500,
  totalMs: 3000,
})
export const T_1035_CARD = turn({
  id: 'turn-1035a',
  occurredAt: '2026-10-26T16:35:30Z',
  askerRole: 'manager',
  tools: [ok('list_time_off_requests', 90), ok('propose_time_off_decision', 110)],
  sectionsRetrieved: ['4.1'],
  sectionsCited: ['4.1'],
  cardAction: 'timeoff.decide',
  inputTokens: 2900,
  cacheReadTokens: 12500,
  outputTokens: 620,
  costUsd: 0.026,
  guardMs: 720,
  firstTextMs: 2000,
  totalMs: 5000,
})
export const T_1035 = turn({
  id: 'turn-1035b',
  occurredAt: '2026-10-26T16:35:00Z',
  askerRole: 'manager',
  tools: [ok('list_time_off_requests', 70)],
  inputTokens: 1400,
  cacheReadTokens: 7800,
  outputTokens: 340,
  costUsd: 0.019,
  guardMs: 650,
  firstTextMs: 1600,
  totalMs: 3200,
})
export const T_1033_CARD = turn({
  id: 'turn-1033',
  occurredAt: '2026-10-26T16:33:00Z',
  tools: [ok('check_time_off', 85), ok('propose_time_off_request', 120)],
  sectionsRetrieved: ['4.1'],
  sectionsCited: ['4.1'],
  cardAction: 'timeoff.request',
  inputTokens: 3140,
  cacheReadTokens: 13100,
  outputTokens: 640,
  costUsd: 0.028,
  guardMs: 700,
  firstTextMs: 2200,
  totalMs: 5800,
})
export const T_1032_AUSTIN = turn({
  id: 'turn-1032',
  occurredAt: '2026-10-26T16:32:00Z',
  askerLocation: 'Austin, TX',
  tools: [ok('search_handbook', 380)],
  sectionsRetrieved: ['4.3', '4.1'],
  sectionsCited: ['4.3'],
  inputTokens: 2000,
  cacheReadTokens: 9000,
  outputTokens: 500,
  costUsd: 0.02,
  guardMs: 620,
  firstTextMs: 1300,
  totalMs: 3900,
})
export const T_1031_ANSWERED = turn({
  id: 'turn-1031',
  occurredAt: '2026-10-26T16:31:00Z',
  tools: [ok('search_handbook', 420)],
  sectionsRetrieved: ['CA-4.3', '4.3', '4.1'],
  sectionsCited: ['CA-4.3'],
  inputTokens: 2200,
  cacheReadTokens: 10200,
  outputTokens: 470,
  costUsd: 0.021,
  guardMs: 640,
  firstTextMs: 1400,
  totalMs: 4100,
})

/** A flagged row: only its date, counts, and timings. Every other field is null. */
export const T_FLAGGED = turn({
  id: 'turn-flagged',
  occurredAt: null,
  flagged: true,
  askerRole: null,
  askerLocation: null,
  outcome: null,
  guardCategory: null,
  injectionSuspected: null,
  tools: null,
  sectionsRetrieved: null,
  sectionsCited: null,
  cardAction: null,
  servedBy: [],
  effort: null,
  promptVersion: null,
  toolsetVersion: null,
  inputTokens: 14800,
  cacheReadTokens: 0,
  outputTokens: 550,
  costUsd: 0.024,
  guardMs: 760,
  firstTextMs: 1900,
  totalMs: 5200,
})

/** A turn that died before the safety check stored a verdict: flagged, but not an escalation. */
export const T_ABANDONED = turn({
  ...T_FLAGGED,
  id: 'turn-abandoned',
  abandoned: true,
  inputTokens: 5200,
  outputTokens: 0,
  costUsd: 0.004,
  guardMs: null,
  firstTextMs: null,
  totalMs: null,
})

// The component card's three more traces.
export const T_0914_REFUSED = turn({
  id: 'turn-0914',
  occurredAt: '2026-10-26T15:14:00Z',
  askerLocation: 'Austin, TX',
  outcome: 'refused',
  refusalCategory: 'general_harms',
  inputTokens: 1100,
  cacheReadTokens: 5100,
  outputTokens: 0,
  costUsd: 0.006,
  guardMs: 610,
  firstTextMs: null,
  totalMs: 1300,
})
export const T_1002_FALLBACK = turn({
  id: 'turn-1002',
  occurredAt: '2026-10-26T16:02:00Z',
  askerRole: 'manager',
  tools: [ok('search_handbook', 410)],
  sectionsRetrieved: ['4.1'],
  sectionsCited: ['4.1'],
  servedBy: ['claude-opus-5-5', 'claude-sonnet-5-5'],
  fallback: true,
  inputTokens: 2500,
  cacheReadTokens: 10400,
  outputTokens: 480,
  costUsd: 0.011,
  guardMs: 660,
  firstTextMs: 3100,
  totalMs: 6200,
})
export const T_0948_FAILED = turn({
  id: 'turn-0948',
  occurredAt: '2026-10-26T15:48:00Z',
  outcome: 'failed',
  tools: [{ name: 'check_time_off', ok: false, durationMs: 3000 }],
  inputTokens: 900,
  cacheReadTokens: 8200,
  outputTokens: 0,
  costUsd: 0.006,
  guardMs: 650,
  firstTextMs: null,
  totalMs: 3800,
})

/** The sample day, as `GET /console/turns` returns it: nine turns, the flagged one last. */
export const DAY_TURNS: ConsoleTurnOut[] = [
  T_1038_INJECTION,
  T_1038_PEOPLE,
  T_1036,
  T_1035_CARD,
  T_1035,
  T_1033_CARD,
  T_1032_AUSTIN,
  T_1031_ANSWERED,
  T_FLAGGED,
]

/** The sample day's tiles. */
export const DAY_METRICS: ConsoleMetricsOut = {
  turns: 9,
  smallSample: true,
  firstToken: { p50Ms: 1640, p95Ms: 2200, targetMs: 3000, sampleSize: 9, smallSample: true },
  safetyCheck: { p95Ms: 980, targetMs: 800, sampleSize: 9, smallSample: true },
  cost: {
    perAnsweredQuestionUsd: 0.0212,
    answeredCount: 8,
    sandboxSpendUsd: 0.21,
    sandboxCapUsd: 1,
    smallSample: true,
  },
  escalation: { rate: 1 / 9, flaggedCount: 1, turns: 9, smallSample: true },
  refusals: {
    rate: 0,
    refusedCount: 0,
    fallbackCount: 0,
    affectedCount: 0,
    turns: 9,
    smallSample: true,
  },
  notFound: { count: 0, turns: 9, sections: [], smallSample: true },
  cardsConfirmed: [
    { action: 'timeoff.request', count: 1 },
    { action: 'timeoff.decide', count: 1 },
    { action: 'timeoff.cancel', count: 0 },
  ],
  injections: { count: 1, turns: 9, smallSample: true },
}

/** Tile 6 filled, over a sample large enough that no tile says "Small sample". */
export const FILLED_METRICS: ConsoleMetricsOut = {
  ...DAY_METRICS,
  turns: 31,
  smallSample: false,
  firstToken: { ...DAY_METRICS.firstToken, sampleSize: 31, smallSample: false },
  safetyCheck: { ...DAY_METRICS.safetyCheck, sampleSize: 31, smallSample: false },
  cost: { ...DAY_METRICS.cost, answeredCount: 27, smallSample: false },
  escalation: { ...DAY_METRICS.escalation, turns: 31, smallSample: false },
  refusals: { ...DAY_METRICS.refusals, turns: 31, smallSample: false },
  notFound: {
    count: 2,
    turns: 31,
    sections: [
      { sectionId: '4.1', count: 2 },
      { sectionId: '5.2', count: 1 },
    ],
    smallSample: false,
  },
  injections: { ...DAY_METRICS.injections, turns: 31, smallSample: false },
}

/** A new sandbox: no turns, so every tile says "No turns yet" and the spend stays. */
export const EMPTY_METRICS: ConsoleMetricsOut = {
  turns: 0,
  smallSample: true,
  firstToken: { p50Ms: null, p95Ms: null, targetMs: 3000, sampleSize: 0, smallSample: true },
  safetyCheck: { p95Ms: null, targetMs: 800, sampleSize: 0, smallSample: true },
  cost: {
    perAnsweredQuestionUsd: null,
    answeredCount: 0,
    sandboxSpendUsd: 0,
    sandboxCapUsd: 1,
    smallSample: true,
  },
  escalation: { rate: null, flaggedCount: 0, turns: 0, smallSample: true },
  refusals: {
    rate: null,
    refusedCount: 0,
    fallbackCount: 0,
    affectedCount: 0,
    turns: 0,
    smallSample: true,
  },
  notFound: { count: 0, turns: 0, sections: [], smallSample: true },
  cardsConfirmed: [
    { action: 'timeoff.request', count: 0 },
    { action: 'timeoff.decide', count: 0 },
    { action: 'timeoff.cancel', count: 0 },
  ],
  injections: { count: 0, turns: 0, smallSample: true },
}
