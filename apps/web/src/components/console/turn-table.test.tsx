import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import {
  DAY_TURNS,
  T_1031_ANSWERED,
  T_1033_CARD,
  T_1038_INJECTION,
  T_ABANDONED,
  T_FLAGGED,
  turn,
} from '@/app/gallery/fixtures/console'
import { TurnTable } from './turn-table'

const ZONE = 'America/Denver'
const props = { timeZone: ZONE }

describe('TurnTable', () => {
  it('is a table with eight column headers, the time column naming the zone', () => {
    render(<TurnTable turns={DAY_TURNS} {...props} />)
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent)).toEqual([
      'Time (MDT)',
      'Asked by',
      'Outcome',
      'Safety check',
      'Tools',
      'Cited',
      'Cost',
      'First token',
    ])
  })

  it('groups rows by day under a heading that counts every row, flagged included', () => {
    const second = turn({
      id: 'next',
      occurredOn: '2026-10-27',
      occurredAt: '2026-10-27T15:00:00Z',
    })
    render(<TurnTable turns={[...DAY_TURNS, second]} {...props} />)
    const headings = screen.getAllByRole('heading', { level: 3 })
    expect(headings.map((h) => h.textContent)).toEqual([
      'Monday, October 26 · 9 turns',
      'Tuesday, October 27 · 1 turn',
    ])
    expect(screen.getAllByRole('table')).toHaveLength(2)
    expect(screen.getAllByRole('table')[0]).toHaveAccessibleName('Monday, October 26 · 9 turns')
  })

  it('keeps the API’s order within each day, flagged rows wherever the API put them', () => {
    const at = (id: string, hour: number) =>
      turn({ id, occurredOn: '2026-10-26', occurredAt: `2026-10-26T${hour}:00:00Z` })
    // Not chronological, as a page boundary could leave them, with a flagged row in the middle.
    const input = [
      at('a', 16),
      at('b', 18),
      { ...T_FLAGGED, id: 'f' },
      at('c', 15),
      turn({ id: 'n', occurredOn: '2026-10-27', occurredAt: '2026-10-27T14:00:00Z' }),
    ]
    render(<TurnTable turns={input} {...props} />)
    const shown = screen
      .getAllByRole('row')
      .filter((r) => r.matches('[data-slot]'))
      .map((r) => r.querySelector('button')?.textContent?.match(/^[\d:]+ [AP]M/)?.[0] ?? 'flagged')
    expect(shown).toEqual(['10:00 AM', '12:00 PM', 'flagged', '9:00 AM', '8:00 AM'])
  })

  it('names the zone from each day’s own rows across a clock change', () => {
    render(
      <TurnTable
        turns={[
          turn({ id: 'a', occurredOn: '2026-10-31', occurredAt: '2026-10-31T16:00:00Z' }),
          turn({ id: 'b', occurredOn: '2026-11-02', occurredAt: '2026-11-02T17:00:00Z' }),
        ]}
        {...props}
      />,
    )
    const heads = screen.getAllByRole('columnheader').filter((h) => /^Time/.test(h.textContent!))
    expect(heads.map((h) => h.textContent)).toEqual(['Time (MDT)', 'Time (MST)'])
  })

  it('announces a day’s heading once: the table carries the label, the wrapper does not', () => {
    render(<TurnTable turns={DAY_TURNS} {...props} />)
    expect(screen.queryByRole('region')).toBeNull()
    expect(screen.getByRole('table')).toHaveAccessibleName('Monday, October 26 · 9 turns')
  })

  it('names every cell without a visible prefix for a phone, hidden at desktop widths', () => {
    render(<TurnTable turns={[T_1031_ANSWERED]} {...props} />)
    const row = screen.getByRole('button').closest('[role="row"]') as HTMLElement
    const hidden = [...row.querySelectorAll('[data-phone-name]')]
    expect(hidden.map((el) => el.textContent?.trim())).toEqual([
      'Time',
      'Asked by',
      'Outcome',
      'Safety check',
      'Cost',
      'First token',
    ])
    // Not displayed at desktop (so the column headers name the cells), visually hidden on a phone.
    for (const el of hidden)
      expect(el).toHaveClass('hidden', 'max-[640px]:inline', 'max-[640px]:sr-only')
    expect(screen.getByRole('button', { name: /^10:31 AM, Employee/ })).toBeInTheDocument()
  })

  it('names each row’s button with the visible time first', () => {
    render(<TurnTable turns={[T_1031_ANSWERED]} {...props} />)
    expect(
      screen.getByRole('button', { name: '10:31 AM, Employee, Oakland, CA, Answered' }),
    ).toHaveTextContent(/^10:31 AM/)
  })

  it('marks the open row on its button, with the trace it controls, and tints the row', () => {
    render(
      <TurnTable
        turns={[T_1031_ANSWERED, T_1033_CARD]}
        selectedId={T_1033_CARD.id}
        traceId="trace"
        {...props}
      />,
    )
    const open = screen.getByRole('button', { name: /^10:33 AM/ })
    expect(open).toHaveAttribute('aria-expanded', 'true')
    expect(open).toHaveAttribute('aria-controls', 'trace')
    expect(open.closest('[role="row"]')).toHaveAttribute('data-selected')
    const other = screen.getByRole('button', { name: /^10:31 AM/ })
    expect(other).toHaveAttribute('aria-expanded', 'false')
    expect(other).not.toHaveAttribute('aria-controls')
    expect(other.closest('[role="row"]')).not.toHaveAttribute('data-selected')
  })

  it('opens a row on a click anywhere in it, once', async () => {
    const onOpen = vi.fn<(id: string) => void>()
    render(<TurnTable turns={[T_1031_ANSWERED]} onOpen={onOpen} {...props} />)
    await userEvent.click(screen.getByText('$0.021'))
    expect(onOpen).toHaveBeenCalledWith(T_1031_ANSWERED.id)
    onOpen.mockClear()
    await userEvent.click(screen.getByRole('button'))
    expect(onOpen).toHaveBeenCalledTimes(1)
  })

  it('opens from the keyboard with Enter on the button', async () => {
    const onOpen = vi.fn<(id: string) => void>()
    render(<TurnTable turns={[T_1031_ANSWERED]} onOpen={onOpen} {...props} />)
    screen.getByRole('button').focus()
    await userEvent.keyboard('{Enter}')
    expect(onOpen).toHaveBeenCalledTimes(1)
  })

  it('shows the facts of a row: tools, cited sections, cost, first token', () => {
    render(<TurnTable turns={[T_1031_ANSWERED]} {...props} />)
    const row = within(screen.getByRole('button').closest('[role="row"]') as HTMLElement)
    expect(row.getByText('CA-4.3')).toBeInTheDocument()
    expect(row.getByText('$0.021')).toBeInTheDocument()
    expect(row.getByText('1.4 s')).toBeInTheDocument()
    expect(row.getByText('Employee')).toBeInTheDocument()
    expect(row.getByText('Oakland, CA')).toBeInTheDocument()
    expect(row.getByText('Answered')).toBeInTheDocument()
    expect(row.getByText('Ordinary')).toBeInTheDocument()
  })

  it('says "Offered a card" only when a card was offered', () => {
    render(<TurnTable turns={[T_1031_ANSWERED, T_1033_CARD]} {...props} />)
    expect(screen.getAllByText('Offered a card')).toHaveLength(1)
  })

  it('shows the injection tag in the safety cell', () => {
    render(<TurnTable turns={[T_1038_INJECTION]} {...props} />)
    expect(screen.getByRole('table')).toHaveTextContent('Possible prompt injection')
  })

  it('shows an empty cell as a dash with a hidden "None"', () => {
    render(<TurnTable turns={[T_1038_INJECTION]} {...props} />)
    const row = screen.getByRole('button').closest('[role="row"]') as HTMLElement
    expect(within(row).getByText('None')).toHaveClass('sr-only')
  })

  it('shows a row that did not produce text with a dash for the first token', () => {
    render(<TurnTable turns={[turn({ firstTextMs: null })]} {...props} />)
    const cells = screen.getAllByRole('cell')
    expect(within(cells[cells.length - 1]!).getByText('None')).toHaveClass('sr-only')
  })

  it('leaves flagged and abandoned rows as plain text, with no control', () => {
    render(<TurnTable turns={[T_FLAGGED, T_ABANDONED]} {...props} />)
    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.getByText(/^Flagged by the safety check/)).toBeInTheDocument()
    expect(screen.getByText(/^This turn didn’t finish/)).toBeInTheDocument()
  })

  it('shows a row with no time as plain text, never as 1970 and never with a button', () => {
    render(<TurnTable turns={[turn({ id: 'x', flagged: false, occurredAt: null })]} {...props} />)
    expect(screen.queryByRole('button')).toBeNull()
    expect(document.body.textContent).not.toMatch(/1970|Dec 31|6:00 PM|5:00 PM/)
  })

  it('docks narrower beside a panel and stacks the tag', () => {
    const { container } = render(<TurnTable turns={[T_1038_INJECTION]} panelOpen {...props} />)
    expect(container.firstElementChild).toHaveAttribute('data-panel')
    expect(container.querySelector('[data-slot="injection-tag"]')).toHaveClass('flex-col')
  })

  it('loads as a header and six skeleton rows, busy, with a hidden status', () => {
    const { container } = render(<TurnTable turns={[]} loading {...props} />)
    expect(screen.getByRole('table')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getAllByRole('columnheader')).toHaveLength(8)
    expect(container.querySelectorAll('[data-slot="turn-skeleton-row"]')).toHaveLength(6)
    expect(screen.getByText('Loading the sandbox figures')).toHaveClass('sr-only')
  })

  it('says there are no questions, with two ways forward', async () => {
    const onAsk = vi.fn<() => void>()
    const onTour = vi.fn<() => void>()
    render(<TurnTable turns={[]} onAskQuestion={onAsk} onTakeTour={onTour} {...props} />)
    expect(
      screen.getByText('No questions yet in this sandbox. Ask something, or take the tour.'),
    ).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Ask a question' }))
    await userEvent.click(screen.getByRole('button', { name: 'Take the tour' }))
    expect(screen.getByRole('button', { name: 'Ask a question' })).toHaveClass('bg-primary')
    expect(screen.getByRole('button', { name: 'Take the tour' })).toHaveClass('bg-surface-raised')
    expect(onAsk).toHaveBeenCalledOnce()
    expect(onTour).toHaveBeenCalledOnce()
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('does not wrap the empty state’s buttons in a status region', () => {
    const { container } = render(<TurnTable turns={[]} {...props} />)
    const empty = container.querySelector('[data-slot="turn-empty"]')!
    expect(empty.tagName).not.toBe('OUTPUT')
    expect(empty.closest('[role="status"], output')).toBeNull()
  })

  it('disables "Take the tour" when the tour cannot start', async () => {
    const onTour = vi.fn<() => void>()
    render(<TurnTable turns={[]} onTakeTour={onTour} tourDisabled {...props} />)
    const button = screen.getByRole('button', { name: 'Take the tour' })
    expect(button).toBeDisabled()
    await userEvent.click(button)
    expect(onTour).not.toHaveBeenCalled()
  })
})
