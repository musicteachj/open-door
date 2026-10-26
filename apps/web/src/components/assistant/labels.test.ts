import { describe, expect, it } from 'vitest'
import type { ToolCallOut } from '@/api/generated'
import { citation } from '@/test/assistant-fixtures'
import {
  HR_SHARED_INBOX,
  QUESTION_LIMIT_CHARACTERS,
  chipLabel,
  conversationCopy,
  failedToolLine,
  formatCount,
  lengthHint,
  sourceName,
  toolIcon,
  toolCallLine,
  toolLine,
  toolRunningLine,
} from './labels'

describe('conversationCopy', () => {
  it('holds the fixed strings from the screen notes and the owner decisions', () => {
    expect(conversationCopy).toMatchObject({
      aiLabel: 'AI',
      assistantName: 'Open Door',
      sources: 'Sources',
      stop: 'Stop',
      stopped: 'Stopped',
      askAgain: 'Ask again',
      retryButton: 'Retry',
      showYourWork: 'Show your work',
      toolsCalled: 'Tools called',
      sectionsRetrieved: 'Sections retrieved',
      none: 'None',
      notCited: 'Not cited',
      safetyOk: 'Safety check: no concerns',
      routed: 'Routed to HR guidance',
      routedNote: 'Questions like this also go to a person on the HR team.',
      retention: 'Conversations are deleted with your sandbox after 24 hours.',
      startNewConversation: 'Start a new conversation',
      startNewSandbox: 'Start a new sandbox',
      tryAgain: 'Try again',
      contactsHeading: 'HR contacts',
      contactsLine: 'A person on the HR team reads and answers these, not the AI.',
      sensitiveLink: 'How confidential HR cases work, §7.2',
      followUpPlaceholder: 'Ask a follow-up question',
      feedbackThanks: 'Thanks for the feedback.',
      sendFailed: 'Something went wrong sending that.',
    })
  })

  it('has the counted strings', () => {
    expect(conversationCopy.citedAs(2)).toBe('Cited as 2')
    expect(conversationCopy.reasonCount(45)).toBe('45 of 500 characters')
  })

  it('has the panel headers and the composer notices', () => {
    expect(conversationCopy.sensitiveHeader).toBe('A person in HR handles this, not the AI')
    expect(conversationCopy.crisisHeader).toBe('Reach a person right now')
    expect(conversationCopy.unavailableHeader).toBe("Can't answer right now")
    expect(conversationCopy.overLimit(2001)).toBe(
      '2,001 of 2,000 characters. Shorten your question to send it.',
    )
    expect(conversationCopy.overLimit(2000)).toBe(
      '2,000 of 2,000 characters. Shorten your question to send it.',
    )
    expect(conversationCopy.longConversation).toBe(
      'This conversation is getting long, so answers may miss details from earlier messages. A new conversation starts clean.',
    )
  })

  it('has no em dash in any string', () => {
    const strings = JSON.stringify(conversationCopy, (_key, value: unknown) =>
      typeof value === 'function' ? (value as (n: number) => string)(1) : value,
    )
    expect(strings).not.toContain(String.fromCharCode(0x2014))
  })
})

describe('toolCallLine', () => {
  const call = (overrides: Partial<ToolCallOut>): ToolCallOut => ({
    name: 'search_handbook',
    inputSummary: "query='sick leave'",
    ok: true,
    durationMs: 1,
    ...overrides,
  })

  it('words a call that worked as its tool line', () => {
    expect(toolCallLine(call({}))).toBe('Searched the handbook: sick leave')
  })

  it('marks a call that failed', () => {
    expect(toolCallLine(call({ ok: false }))).toBe('Searched the handbook: sick leave (failed)')
  })

  it('does not mark the skipped-steps entry as failed, though the API sends it with ok false', () => {
    expect(
      toolCallLine(call({ name: 'skipped', inputSummary: '3 calls not run (limit)', ok: false })),
    ).toBe('Skipped 3 more steps (the limit for one question)')
  })
})

describe('failedToolLine', () => {
  it('marks a tool line as failed', () => {
    expect(failedToolLine('Searched the handbook: sick leave')).toBe(
      'Searched the handbook: sick leave (failed)',
    )
  })
})

describe('the disabled composer line', () => {
  it('is one sentence, in parts so the page can link Handbook and Directory', () => {
    expect(conversationCopy.stillUseParts.join('')).toBe(
      'You can still use the Handbook and the Directory.',
    )
    expect(conversationCopy.stillUseParts[1]).toBe('Handbook')
    expect(conversationCopy.stillUseParts[3]).toBe('Directory')
  })
})

describe('HR_SHARED_INBOX', () => {
  it('is the fixed inbox shown after the directory HR people', () => {
    expect(HR_SHARED_INBOX).toEqual({
      name: 'HR team',
      role: 'Shared inbox',
      workEmail: 'hr@juniperrow.example',
    })
  })
})

describe('chipLabel', () => {
  it('names an addendum section with its group', () => {
    expect(chipLabel(citation())).toBe('Handbook CA-4.3 · California addendum')
  })

  it('names a company section with its number and group', () => {
    expect(chipLabel(citation({ sectionId: '4.3', groupName: 'Time off' }))).toBe(
      'Handbook §4.3 · Time off',
    )
  })
})

describe('sourceName', () => {
  it('is the marker, then the section and group with a comma', () => {
    expect(sourceName(1, citation())).toBe('Source 1: Handbook CA-4.3, California addendum')
    expect(sourceName(2, citation({ sectionId: '4.3', groupName: 'Time off' }))).toBe(
      'Source 2: Handbook §4.3, Time off',
    )
  })
})

describe('toolLine: the steps the question limit skipped', () => {
  it('says how many steps were skipped, and why', () => {
    expect(toolLine('skipped', '3 calls not run (limit)')).toBe(
      'Skipped 3 more steps (the limit for one question)',
    )
  })

  it('uses the singular for one', () => {
    expect(toolLine('skipped', '1 calls not run (limit)')).toBe(
      'Skipped 1 more step (the limit for one question)',
    )
  })

  it('has a plain line when the count cannot be read', () => {
    for (const summary of ['', 'some calls not run', '0 calls not run (limit)', '-2 calls']) {
      expect(toolLine('skipped', summary)).toBe('Skipped some steps (the limit for one question)')
    }
  })

  it('never shows the raw summary', () => {
    expect(toolLine('skipped', '3 calls not run (limit)')).not.toContain('calls not run')
  })
})

describe('toolLine', () => {
  it('words a handbook search with its query', () => {
    expect(toolLine('search_handbook', "query='sick leave'")).toBe(
      'Searched the handbook: sick leave',
    )
  })

  it('ignores the location, which the line does not need', () => {
    expect(toolLine('search_handbook', "query='sick leave', location=CA")).toBe(
      'Searched the handbook: sick leave',
    )
  })

  it('reads a double-quoted repr, which Python uses when the query has an apostrophe', () => {
    expect(toolLine('search_handbook', 'query="what\'s my rate"')).toBe(
      "Searched the handbook: what's my rate",
    )
  })

  it('reads an escaped quote in a single-quoted repr', () => {
    expect(toolLine('search_handbook', "query='it\\'s a \"test\"'")).toBe(
      'Searched the handbook: it\'s a "test"',
    )
  })

  it('reads an escaped backslash', () => {
    expect(toolLine('search_handbook', "query='a\\\\b'")).toBe('Searched the handbook: a\\b')
  })

  it('reads the other escapes Python writes', () => {
    expect(toolLine('search_handbook', "query='a\\tb\\x41\\u00e9'")).toBe(
      'Searched the handbook: a\tbAé',
    )
  })

  it('keeps the trailing ellipsis of a shortened query', () => {
    expect(toolLine('search_handbook', "query='how many sick days do I get in a…'")).toBe(
      'Searched the handbook: how many sick days do I get in a…',
    )
  })

  it('keeps a comma and an equals sign inside the query', () => {
    expect(toolLine('search_handbook', "query='a, location=b'")).toBe(
      'Searched the handbook: a, location=b',
    )
  })

  it('falls back to the plain line when the query is missing, empty, or unterminated', () => {
    expect(toolLine('search_handbook', '')).toBe('Searched the handbook')
    expect(toolLine('search_handbook', "query=''")).toBe('Searched the handbook')
    expect(toolLine('search_handbook', "query='never closed")).toBe('Searched the handbook')
    expect(toolLine('search_handbook', 'location=CA')).toBe('Searched the handbook')
  })

  it('never shows the raw summary, whatever it holds', () => {
    expect(toolLine('search_handbook', "query=sick leave, 'x'")).toBe('Searched the handbook')
  })

  it('reads the profile with no details', () => {
    expect(toolLine('get_my_profile', 'own profile')).toBe('Read your profile')
    expect(toolLine('get_my_profile', '')).toBe('Read your profile')
  })

  it('words a directory lookup, with the query when there is one', () => {
    expect(toolLine('find_people', "scope=everyone, query='Elena'")).toBe(
      'Looked up the directory: Elena',
    )
    expect(toolLine('find_people', 'scope=my_team')).toBe('Looked up the directory')
    expect(toolLine('find_people', 'garbage')).toBe('Looked up the directory')
  })

  it('words the time-off reads as one line, with no summary text', () => {
    for (const name of ['get_time_off_balance', 'list_time_off_requests', 'check_time_off']) {
      expect(toolLine(name, 'anything')).toBe('Checked your time off')
    }
  })

  it('words the propose tools as a confirm card and never shows a request id', () => {
    const id = '3f2a1b4c-5d6e-4f70-8a9b-0c1d2e3f4a5b'
    for (const name of [
      'propose_time_off_request',
      'propose_time_off_decision',
      'propose_cancel_time_off',
    ]) {
      const line = toolLine(name, `approve request ${id}`)
      expect(line).toBe('Prepared a confirm card')
      expect(line).not.toContain(id)
    }
  })

  it('falls back to a generic line for an unknown tool, never the raw summary', () => {
    expect(toolLine('delete_everything', "query='x'")).toBe('Used a tool')
    expect(toolLine('', '')).toBe('Used a tool')
  })
})

describe('toolIcon', () => {
  it('names the icon for each tool', () => {
    expect(toolIcon('search_handbook')).toBe('search')
    expect(toolIcon('get_my_profile')).toBe('profile')
    expect(toolIcon('find_people')).toBe('people')
    expect(toolIcon('check_time_off')).toBe('calendar')
    expect(toolIcon('get_time_off_balance')).toBe('calendar')
    expect(toolIcon('list_time_off_requests')).toBe('calendar')
    expect(toolIcon('propose_time_off_request')).toBe('card')
    expect(toolIcon('propose_time_off_decision')).toBe('card')
    expect(toolIcon('propose_cancel_time_off')).toBe('card')
  })

  it('has a generic icon for an unknown tool', () => {
    expect(toolIcon('something_else')).toBe('tool')
  })

  it('has the generic icon for a name an object inherits, not the inherited member', () => {
    for (const name of ['constructor', '__proto__', 'toString', 'hasOwnProperty', 'valueOf']) {
      expect(toolIcon(name)).toBe('tool')
    }
  })
})

describe('formatCount', () => {
  it('writes thousands with a comma', () => {
    expect(formatCount(0)).toBe('0')
    expect(formatCount(999)).toBe('999')
    expect(formatCount(1962)).toBe('1,962')
    expect(formatCount(2000)).toBe('2,000')
  })
})

describe('lengthHint', () => {
  it('shows the count against the limit', () => {
    expect(QUESTION_LIMIT_CHARACTERS).toBe(2000)
    expect(lengthHint(1962)).toBe('1,962 of 2,000 characters')
  })
})

describe('toolRunningLine', () => {
  it('words a search in the present tense, and "again" for a later one', () => {
    expect(toolRunningLine('search_handbook', false)).toBe('Searching the handbook…')
    expect(toolRunningLine('search_handbook', true)).toBe('Searching the handbook again…')
  })

  it('words the other tools', () => {
    expect(toolRunningLine('get_my_profile', false)).toBe('Looking up your profile…')
    expect(toolRunningLine('find_people', false)).toBe('Searching the directory…')
    expect(toolRunningLine('find_people', true)).toBe('Searching the directory again…')
  })

  it('words the time-off tools in the present tense', () => {
    expect(toolRunningLine('check_time_off', false)).toBe('Checking your time off…')
    expect(toolRunningLine('get_time_off_balance', true)).toBe('Checking your time off again…')
    expect(toolRunningLine('propose_time_off_request', false)).toBe('Preparing a confirm card…')
    expect(toolRunningLine('propose_cancel_time_off', false)).toBe('Preparing a confirm card…')
  })

  it('gives an unknown tool a plain line', () => {
    expect(toolRunningLine('something_new', false)).toBe('Working…')
  })
})
