import { act, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { TimelineEntryOut } from '@/api/generated'
import { ANNOUNCE_DELAY_MS, resetAnnouncer } from '@/lib/announce'
import { CaseTimeline, type CaseTimelineProps } from './case-timeline'
import { timelineEntryText } from './timeline-text'

const TZ = 'America/Denver'

function entry(over: Partial<TimelineEntryOut>): TimelineEntryOut {
  return {
    kind: 'opened',
    occurredAt: '2026-10-26T16:41:00Z',
    actorPersonId: null,
    actorGivenName: null,
    actorFamilyName: null,
    fromStatus: null,
    toStatus: null,
    ...over,
  }
}
const dana = { actorPersonId: 'd', actorGivenName: 'Dana', actorFamilyName: 'Whitfield' }

const BASE: TimelineEntryOut[] = [
  entry({ kind: 'opened', actorGivenName: 'Priya', actorFamilyName: 'Raman' }),
  entry({ kind: 'summary_written' }),
  entry({ kind: 'viewed', occurredAt: '2026-10-26T16:52:00Z', ...dana }),
]

function props(over: Partial<CaseTimelineProps> = {}): CaseTimelineProps {
  return {
    entries: BASE,
    screening: null,
    personName: 'Priya Raman',
    timeZone: TZ,
    ...over,
  }
}

const lines = () => within(screen.getByRole('list')).getAllByRole('listitem')

describe('CaseTimeline', () => {
  it('is a section with a Timeline heading and a list, oldest first', () => {
    render(<CaseTimeline {...props()} />)
    expect(screen.getByRole('region', { name: 'Timeline' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Timeline' })).toBeInTheDocument()
    expect(lines().map((li) => li.textContent)).toEqual([
      'Sent by Priya RamanMon, Oct 26, 10:41 AM MDT',
      'AI summary written10:41 AM MDT',
      'Dana Whitfield read the AI summary10:52 AM MDT',
    ])
  })

  it('names each kind of event', () => {
    const text = (e: Partial<TimelineEntryOut>) =>
      timelineEntryText(entry(e), { personName: 'Priya Raman' })
    expect(text({ kind: 'summary_failed' })).toBe('AI summary couldn’t be written')
    expect(text({ kind: 'text_read', ...dana })).toBe('Dana Whitfield read Priya’s words')
    expect(text({ kind: 'status_changed', toStatus: 'in_review', ...dana })).toBe(
      'Dana Whitfield started the review',
    )
    expect(text({ kind: 'status_changed', toStatus: 'closed', ...dana })).toBe(
      'Dana Whitfield closed the case',
    )
    expect(text({ kind: 'opened' })).toBe('Sent by Priya Raman')
  })

  it('shows the date again when the day changes, and the time alone otherwise', () => {
    render(
      <CaseTimeline
        {...props({
          entries: [
            ...BASE,
            entry({ kind: 'text_read', occurredAt: '2026-10-27T14:05:00Z', ...dana }),
            entry({
              kind: 'status_changed',
              toStatus: 'in_review',
              occurredAt: '2026-10-27T14:09:00Z',
              ...dana,
            }),
          ],
        })}
      />,
    )
    expect(lines().map((li) => li.lastElementChild!.textContent)).toEqual([
      'Mon, Oct 26, 10:41 AM MDT',
      '10:41 AM MDT',
      '10:52 AM MDT',
      'Tue, Oct 27, 8:05 AM MDT',
      '8:09 AM MDT',
    ])
  })

  it('compares days in the viewer’s zone, not UTC', () => {
    render(
      <CaseTimeline
        {...props({
          entries: [
            entry({ occurredAt: '2026-10-27T01:00:00Z' }), // Oct 26, 7 PM in Denver
            entry({ kind: 'summary_written', occurredAt: '2026-10-27T02:00:00Z' }), // still Oct 26
          ],
        })}
      />,
    )
    expect(lines()[1]!.lastElementChild!.textContent).toBe('8:00 PM MDT')
  })

  it('puts the crisis line after "Sent by", from the screening', () => {
    render(<CaseTimeline {...props({ screening: 'crisis' })} />)
    expect(lines().map((li) => li.firstElementChild!.textContent)).toEqual([
      'Sent by Priya Raman',
      'The safety check routed it to crisis text',
      'AI summary written',
      'Dana Whitfield read the AI summary',
    ])
    expect(lines()[1]!.lastElementChild!.textContent).toBe('10:41 AM MDT')
  })

  it('marks only the newest entry', () => {
    render(<CaseTimeline {...props()} />)
    const marked = lines().filter((li) => li.hasAttribute('data-latest'))
    expect(marked).toHaveLength(1)
    expect(marked[0]).toBe(lines().at(-1))
    expect(marked[0]!.className).toContain('before:border-primary')
  })
})

describe('CaseTimeline announcements', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => {
    vi.useRealTimers()
    resetAnnouncer()
  })

  const announcement = () => document.querySelector('[aria-live="polite"]')?.textContent ?? ''
  const settle = () => act(() => vi.advanceTimersByTimeAsync(ANNOUNCE_DELAY_MS + 10))

  it('announces nothing on mount', async () => {
    render(<CaseTimeline {...props()} />)
    await settle()
    expect(announcement()).toBe('')
  })

  it('announces an entry added after mount, politely and once', async () => {
    const { rerender } = render(<CaseTimeline {...props()} />)
    const added = entry({ kind: 'text_read', occurredAt: '2026-10-26T16:53:00Z', ...dana })
    rerender(<CaseTimeline {...props({ entries: [...BASE, added] })} />)
    await settle()
    expect(announcement()).toBe('Added to the timeline: Dana Whitfield read Priya’s words')
    // The same entries again (a refetch) say nothing more.
    rerender(<CaseTimeline {...props({ entries: [...BASE, { ...added }] })} />)
    await act(() => vi.advanceTimersByTimeAsync(8000))
    expect(announcement()).toBe('')
  })

  it('does not announce an added "read the AI summary" entry, which a refetch adds', async () => {
    const { rerender } = render(<CaseTimeline {...props()} />)
    const viewed = entry({ kind: 'viewed', occurredAt: '2026-10-26T17:00:00Z', ...dana })
    rerender(<CaseTimeline {...props({ entries: [...BASE, viewed] })} />)
    await settle()
    expect(announcement()).toBe('')
    expect(lines()).toHaveLength(4)
  })

  it('announces a status change once', async () => {
    const { rerender } = render(<CaseTimeline {...props()} />)
    const changed = entry({
      kind: 'status_changed',
      toStatus: 'closed',
      occurredAt: '2026-10-26T17:10:00Z',
      ...dana,
    })
    rerender(<CaseTimeline {...props({ entries: [...BASE, changed] })} />)
    await settle()
    expect(announcement()).toBe('Added to the timeline: Dana Whitfield closed the case')
  })

  it('announces a second identical entry added after mount', async () => {
    const changed = entry({
      kind: 'status_changed',
      toStatus: 'closed',
      occurredAt: '2026-10-26T17:10:00Z',
      ...dana,
    })
    const { rerender } = render(<CaseTimeline {...props({ entries: [...BASE, changed] })} />)
    rerender(<CaseTimeline {...props({ entries: [...BASE, changed, { ...changed }] })} />)
    await settle()
    expect(announcement()).toBe('Added to the timeline: Dana Whitfield closed the case')
    expect(lines()).toHaveLength(5)
  })

  it('announces nothing when entries only reorder or stay', async () => {
    const { rerender } = render(<CaseTimeline {...props()} />)
    rerender(<CaseTimeline {...props({ entries: [...BASE] })} />)
    await settle()
    expect(announcement()).toBe('')
  })
})

describe('CaseTimeline: a crisis case has no summary to fail', () => {
  const failed = [
    entry({ kind: 'opened', actorGivenName: 'Priya', actorFamilyName: 'Raman' }),
    entry({ kind: 'summary_failed' }),
  ]

  it('leaves out "AI summary couldn’t be written" for a crisis case', () => {
    render(<CaseTimeline {...props({ entries: failed, screening: 'crisis' })} />)
    const texts = lines().map((line) => line.textContent)
    expect(texts.some((text) => /summary couldn.t be written/.test(text ?? ''))).toBe(false)
    expect(texts).toHaveLength(2)
    expect(texts[1]).toContain('The safety check routed it to crisis text')
  })

  it('still shows it for any other case', () => {
    render(<CaseTimeline {...props({ entries: failed })} />)
    expect(lines().some((line) => /summary couldn.t be written/.test(line.textContent ?? ''))).toBe(
      true,
    )
  })
})
