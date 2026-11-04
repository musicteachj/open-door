import { describe, expect, it } from 'vitest'
import type { ConsoleTurnOut } from '@/api/generated'
import {
  cardActionLabel,
  cardActionPlural,
  dayHeading,
  formatDuration,
  formatFirstToken,
  formatPercent,
  formatSpend,
  formatTarget,
  formatTurnCost,
  redactedFacts,
  refusalLabel,
  roleLabel,
  rowTime,
  shortDay,
  toolLabel,
  totalInputTokens,
  tracedInputTokens,
  turnName,
  turnTitle,
  zoneAbbreviation,
} from './labels'

const base: ConsoleTurnOut = {
  id: 'a',
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
  inputTokens: 14800,
  outputTokens: 550,
  cacheReadTokens: 0,
  cacheWriteTokens: 0,
  costUsd: 0.024,
  guardMs: 760,
  firstTextMs: 1900,
  totalMs: 5200,
}

describe('toolLabel', () => {
  it.each([
    ['get_time_off_balance', 'Checked time off'],
    ['list_time_off_requests', 'Checked time off'],
    ['check_time_off', 'Checked time off'],
    ['propose_time_off_request', 'Prepared a confirm card'],
    ['propose_time_off_decision', 'Prepared a confirm card'],
    ['propose_cancel_time_off', 'Prepared a confirm card'],
    ['find_people', 'Looked up the directory'],
    ['search_handbook', 'Searched the handbook'],
    ['get_my_profile', 'Read the profile'],
    ['get_my_cases', 'Checked cases'],
    ['list_cases', 'Checked cases'],
    ['something_new', 'Used a tool'],
    ['toString', 'Used a tool'],
  ])('%s is "%s"', (name, label) => expect(toolLabel(name)).toBe(label))
})

describe('card actions', () => {
  it('words each action, and keeps one it does not know', () => {
    expect(cardActionLabel('timeoff.request')).toBe('Time-off request')
    expect(cardActionLabel('timeoff.decide')).toBe('Time-off decision')
    expect(cardActionLabel('timeoff.cancel')).toBe('Time-off cancellation')
    expect(cardActionLabel('other.thing')).toBe('other.thing')
  })

  it('words the plurals for the Cards confirmed tile', () => {
    expect(cardActionPlural('timeoff.request')).toBe('Time-off requests')
    expect(cardActionPlural('timeoff.decide')).toBe('Decisions')
    expect(cardActionPlural('timeoff.cancel')).toBe('Cancellations')
  })
})

describe('words for a row', () => {
  it('names the roles', () => {
    expect(roleLabel('employee')).toBe('Employee')
    expect(roleLabel('manager')).toBe('Manager')
    expect(roleLabel('hr')).toBe('HR')
  })

  it('shows a refusal category with spaces', () => {
    expect(refusalLabel('general_harms')).toBe('general harms')
  })
})

describe('numbers', () => {
  it('shows a turn cost to three decimals and spend to two', () => {
    expect(formatTurnCost(0.0212)).toBe('$0.021')
    expect(formatTurnCost(0.006)).toBe('$0.006')
    expect(formatSpend(0.2104, 1)).toBe('$0.21 of $1.00 cap')
    expect(formatSpend(0, 1)).toBe('$0.00 of $1.00 cap')
  })

  it('shows under a second in ms and the rest in seconds with one decimal', () => {
    expect(formatDuration(980)).toBe('980 ms')
    expect(formatDuration(999)).toBe('999 ms')
    expect(formatDuration(999.4)).toBe('999 ms')
    expect(formatDuration(999.6)).toBe('1.0 s')
    expect(formatDuration(1000)).toBe('1.0 s')
    expect(formatDuration(1640)).toBe('1.6 s')
    expect(formatDuration(5200)).toBe('5.2 s')
  })

  it('shows a target without a trailing decimal', () => {
    expect(formatTarget(3000)).toBe('3 s')
    expect(formatTarget(800)).toBe('800 ms')
    expect(formatTarget(2500)).toBe('2.5 s')
  })

  it('says "No answer text" for a missing first token', () => {
    expect(formatFirstToken(null)).toBe('No answer text')
    expect(formatFirstToken(1900)).toBe('1.9 s')
  })

  it('rounds a rate to a whole percent', () => {
    expect(formatPercent(0.1111)).toBe('11%')
    expect(formatPercent(0)).toBe('0%')
    expect(formatPercent(1 / 300)).toBe('Under 1%')
    expect(formatPercent(0.005)).toBe('1%')
    expect(formatPercent(199 / 200)).toBe('Over 99%')
    expect(formatPercent(0.994)).toBe('99%')
    expect(formatPercent(1)).toBe('100%')
  })
})

describe('times', () => {
  it('shows a row time in the zone, without the abbreviation', () => {
    expect(rowTime('2026-10-26T16:31:00Z', 'America/Denver')).toBe('10:31 AM')
    expect(rowTime('2026-10-26T16:31:00Z', 'America/Chicago')).toBe('11:31 AM')
  })

  it('names the zone from the date, since daylight time moves it', () => {
    expect(zoneAbbreviation('America/Denver', '2026-10-26T16:31:00Z')).toBe('MDT')
    expect(zoneAbbreviation('America/Denver', '2026-12-01T16:31:00Z')).toBe('MST')
  })

  it('words a day heading with its count, flagged rows included', () => {
    expect(dayHeading('2026-10-26', 9)).toBe('Monday, October 26 · 9 turns')
    expect(dayHeading('2026-10-27', 1)).toBe('Tuesday, October 27 · 1 turn')
    expect(shortDay('2026-10-26')).toBe('Oct 26')
  })
})

describe('a turn’s names', () => {
  it('names the row for a screen reader, visible text first', () => {
    expect(turnName(base, 'America/Denver')).toEqual({
      time: '10:31 AM',
      hidden: ', Employee, Oakland, CA, Answered',
    })
  })

  it('titles the trace with the time, role, and place', () => {
    expect(turnTitle(base, 'America/Denver')).toBe('10:31 AM · Employee · Oakland, CA')
  })

  it('writes the redacted facts, dropping a timing that is null', () => {
    const flagged: ConsoleTurnOut = {
      ...base,
      flagged: true,
      occurredAt: null,
      outcome: null,
      totalMs: 5200,
    }
    expect(redactedFacts(flagged)).toBe(
      'Oct 26 · 14,800 input tokens · 550 output · $0.024 · safety check 760 ms · first token 1.9 s · total 5.2 s',
    )
    expect(redactedFacts({ ...flagged, guardMs: null, firstTextMs: null, totalMs: null })).toBe(
      'Oct 26 · 14,800 input tokens · 550 output · $0.024',
    )
  })
})

describe('tracedInputTokens', () => {
  it('adds the cache reads, not the writes, to the plain input', () => {
    expect(
      tracedInputTokens({ ...base, inputTokens: 100, cacheReadTokens: 50, cacheWriteTokens: 25 }),
    ).toBe(150)
  })
})

describe('totalInputTokens', () => {
  it('adds the cache reads and writes to the plain input', () => {
    expect(
      totalInputTokens({ ...base, inputTokens: 2200, cacheReadTokens: 10200, cacheWriteTokens: 0 }),
    ).toBe(12400)
    expect(
      totalInputTokens({ ...base, inputTokens: 100, cacheReadTokens: 50, cacheWriteTokens: 25 }),
    ).toBe(175)
  })
})
