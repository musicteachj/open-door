// The conversation's words, in one tested place (the "Copy not given in the brief" and "Build
// decisions" sections of docs/design/screens/07-conversation/notes.md). Status lines, error
// messages, and the escalation messages come from the API, so they are not here. A component calls
// these instead of building its own string.
import type { CitationOut, ToolCallOut } from '@/api/generated'
import { sectionNumber } from '@/components/handbook/labels'

/** The longest question the composer sends, from the API's own limit. */
export const QUESTION_LIMIT_CHARACTERS = 2000

/** The longest feedback reason the API takes. */
export const REASON_LIMIT_CHARACTERS = 500

/** The count with a thousands comma: 1962 is "1,962". */
export function formatCount(count: number): string {
  return new Intl.NumberFormat('en-US').format(count)
}

const STILL_USE_PARTS = [
  'You can still use the ',
  'Handbook',
  ' and the ',
  'Directory',
  '.',
] as const

/** "1,962 of 2,000 characters": a count against its limit, the one way every counter says it. */
function charactersOf(count: number, limit: number): string {
  return `${formatCount(count)} of ${formatCount(limit)} characters`
}

export const conversationCopy = {
  // The assistant's message
  aiLabel: 'AI',
  assistantName: 'Open Door',
  youAsked: 'You asked: ',
  sources: 'Sources',
  stop: 'Stop',
  stopped: 'Stopped',
  askAgain: 'Ask again',
  // Not `retry`: src/lib/no-retry-overrides.test.ts bans that key for query options.
  retryButton: 'Retry',
  // There is no design for an answer the output limit cut off. A calm line, for the owner to review.
  incomplete: 'This answer was cut off before it finished.',

  // "Show your work"
  showYourWork: 'Show your work',
  toolsCalled: 'Tools called',
  sectionsRetrieved: 'Sections retrieved',
  none: 'None',
  citedAs: (marker: number) => `Cited as ${marker}`,
  notCited: 'Not cited',
  safetyOk: 'Safety check: no concerns',
  routed: 'Routed to HR guidance',
  routedNote: 'Questions like this also go to a person on the HR team.',

  // Feedback. The thank-you is the same after Yes and after a reason (owner decision).
  feedbackQuestion: 'Was this right?',
  yes: 'Yes',
  no: 'No',
  feedbackThanks: 'Thanks for the feedback.',
  reasonLabel: 'What was wrong?',
  optional: 'Optional',
  reasonPlaceholder: 'For example, it cited the wrong state',
  reasonCount: (count: number) => charactersOf(count, REASON_LIMIT_CHARACTERS),
  cancel: 'Cancel',
  sendFeedback: 'Send feedback',

  // The panels
  sensitiveHeader: 'A person in HR handles this, not the AI',
  sensitiveLink: 'How confidential HR cases work, §7.2',
  crisisHeader: 'Reach a person right now',
  unavailableHeader: "Can't answer right now",
  tryAgain: 'Try again',
  contactsHeading: 'HR contacts',
  contactsLine: 'A person on the HR team reads and answers these, not the AI.',

  // The conversation view and the composer
  retention: 'Conversations are deleted with your sandbox after 24 hours.',
  startNewConversation: 'Start a new conversation',
  followUpPlaceholder: 'Ask a follow-up question',
  sandboxDisabledPlaceholder: "The assistant isn't available in this sandbox.",
  dailyDisabledPlaceholder: "The assistant isn't available until tomorrow.",
  // "You can still use the Handbook and the Directory." in parts, so the composer can link
  // "Handbook" and "Directory".
  stillUseParts: STILL_USE_PARTS,
  startNewSandbox: 'Start a new sandbox',
  // The design's "at the limit" text, with the real count. The API takes exactly 2,000, so this
  // shows from 2,001, and the question can't be sent until it is shortened.
  overLimit: (count: number) =>
    `${charactersOf(count, QUESTION_LIMIT_CHARACTERS)}. Shorten your question to send it.`,
  // Spoken (not shown) when a question that was over the limit is short enough again.
  underLimitAgain: 'Back under the limit.',
  longConversation:
    'This conversation is getting long, so answers may miss details from earlier messages. A new conversation starts clean.',
} as const

/** "1,962 of 2,000 characters", shown from 1,800 characters. */
export function lengthHint(count: number): string {
  return charactersOf(count, QUESTION_LIMIT_CHARACTERS)
}

/**
 * The shared HR inbox (owner decision): a fixed entry shown after the directory's HR people in
 * every panel's contacts.
 */
export const HR_SHARED_INBOX = {
  name: 'HR team',
  role: 'Shared inbox',
  workEmail: 'hr@juniperrow.example',
} as const

/** A source chip's text: "Handbook CA-4.3 · California addendum", "Handbook §4.3 · Time off". */
export function chipLabel(citation: Pick<CitationOut, 'sectionId' | 'groupName'>): string {
  return `Handbook ${sectionNumber(citation.sectionId)} · ${citation.groupName}`
}

/** A marker's or chip's accessible name: "Source 1: Handbook CA-4.3, California addendum". */
export function sourceName(
  marker: number,
  citation: Pick<CitationOut, 'sectionId' | 'groupName'>,
): string {
  return `Source ${marker}: Handbook ${sectionNumber(citation.sectionId)}, ${citation.groupName}`
}

export type ToolIconKind = 'search' | 'profile' | 'people' | 'tool'

const TOOL_ICONS: Record<string, ToolIconKind> = {
  search_handbook: 'search',
  get_my_profile: 'profile',
  find_people: 'people',
}

/** Which icon a tool gets in "Show your work". An unknown tool gets the generic one. */
export function toolIcon(name: string): ToolIconKind {
  return Object.hasOwn(TOOL_ICONS, name) ? TOOL_ICONS[name]! : 'tool'
}

const PYTHON_ESCAPES: Record<string, string> = { n: '\n', r: '\r', t: '\t' }

/**
 * Reads the Python string literal at the start of `source` (the API writes a query with repr(),
 * so it is single- or double-quoted, with backslash escapes) and returns its text. Returns null
 * when `source` doesn't start with a closed literal.
 */
function readPythonString(source: string): string | null {
  const quote = source[0]
  if (quote !== "'" && quote !== '"') return null
  let text = ''
  for (let i = 1; i < source.length; i++) {
    const char = source[i]!
    if (char === quote) return text
    if (char !== '\\') {
      text += char
      continue
    }
    const next = source[++i]
    const hexLength = next === 'x' ? 2 : next === 'u' ? 4 : next === 'U' ? 8 : 0
    if (hexLength > 0) {
      const hex = source.slice(i + 1, i + 1 + hexLength)
      const code = /^[0-9a-fA-F]+$/.test(hex) && hex.length === hexLength ? parseInt(hex, 16) : NaN
      if (Number.isNaN(code) || code > 0x10ffff) return null
      text += String.fromCodePoint(code)
      i += hexLength
    } else if (next === undefined) {
      return null
    } else {
      text += PYTHON_ESCAPES[next] ?? next
    }
  }
  return null
}

/** The query in a tool summary, or null when it has none or can't be read. */
function queryOf(inputSummary: string, prefix: RegExp): string | null {
  const match = prefix.exec(inputSummary)
  if (!match) return null
  const query = readPythonString(inputSummary.slice(match[0].length))
  return query === null || query.trim() === '' ? null : query
}

/** A tool's line when the call failed, so the trace doesn't read as if it had worked. */
export function failedToolLine(line: string): string {
  return `${line} (failed)`
}

function withDetail(line: string, detail: string | null): string {
  return detail === null ? line : `${line}: ${detail}`
}

/**
 * One line of "Show your work" from a tool's name and its machine-shaped summary (for example
 * "query='sick leave', location=CA"). The summary is read, never shown: an unknown tool, or a
 * summary that can't be read, gets a plain line instead of the raw text. A search leaves its
 * location out, and the profile line carries no details, so no private data enters the trace.
 */
export function toolLine(name: string, inputSummary: string): string {
  switch (name) {
    case 'search_handbook':
      return withDetail('Searched the handbook', queryOf(inputSummary, /^query=/))
    case 'get_my_profile':
      return 'Read your profile'
    case 'find_people':
      return withDetail('Looked up the directory', queryOf(inputSummary, /^scope=\w+, query=/))
    case 'skipped': {
      // The API's own entry for calls the per-question limit stopped: "3 calls not run (limit)".
      const count = /^(\d+) calls? not run/.exec(inputSummary)
      const skipped = count ? Number(count[1]) : 0
      if (skipped < 1) return 'Skipped some steps (the limit for one question)'
      return `Skipped ${skipped} more ${skipped === 1 ? 'step' : 'steps'} (the limit for one question)`
    }
    default:
      return 'Used a tool'
  }
}

/**
 * A tool call's line in "Show your work": its `toolLine`, marked as failed when the call failed.
 * The skipped-steps entry is sent with `ok` false, but nothing failed there (the limit stopped the
 * calls before they ran), so it is never marked.
 */
export function toolCallLine(call: Pick<ToolCallOut, 'name' | 'inputSummary' | 'ok'>): string {
  const line = toolLine(call.name, call.inputSummary)
  return call.ok || call.name === 'skipped' ? line : failedToolLine(line)
}
