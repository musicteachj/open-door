import { within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { ConsoleSections } from './console-sections'

// The browser tests address each state by its heading's id, so the ids are part of the contract.
const IDS = [
  'console-outcome-badges',
  'console-safety-labels',
  'console-tile-normal',
  'console-tile-small-sample',
  'console-tile-above-target',
  'console-tile-no-turns',
  'console-tile-sections',
  'console-tile-loading',
  'console-tiles-day',
  'console-tiles-filled',
  'console-tiles-empty',
  'console-tiles-loading',
  'console-table-rows',
  'console-table-selected',
  'console-table-flagged',
  'console-table-loading',
  'console-table-empty',
  'console-error',
  'console-trace-answered',
  'console-trace-card',
  'console-trace-injection',
  'console-trace-refused',
  'console-trace-fallback',
  'console-trace-failed-tool',
  'console-live',
  'console-scoreboard',
  'console-scoreboard-rows',
]

const section = (id: string) => within(document.getElementById(id)!.closest('section')!)

describe('ConsoleSections', () => {
  it('has a heading with a stable id for every state, in page order', () => {
    const { container } = render(<ConsoleSections />)
    const found = [...container.querySelectorAll('h3[id]')]
      .map((heading) => heading.id)
      .filter((id) => /^[a-z][a-z0-9-]*$/.test(id))
    expect(found).toEqual(IDS)
  })

  it('does not take focus', () => {
    render(<ConsoleSections />)
    expect(document.body).toHaveFocus()
  })

  it('shows every outcome badge', () => {
    render(<ConsoleSections />)
    expect(
      section('console-outcome-badges').getAllByText(
        /^(Answered|Said the handbook|Refused|Stopped|Failed|Spending|Safety check unavailable)/,
      ),
    ).toHaveLength(7)
  })

  it('holds the live console: open, swap, and close with focus returning', async () => {
    render(<ConsoleSections />)
    const live = section('console-live')
    await userEvent.click(live.getByRole('button', { name: /^10:33 AM/ }))
    expect(live.getByRole('heading', { level: 2, name: /^10:33 AM/ })).toHaveFocus()
    await userEvent.click(live.getByRole('button', { name: /^10:31 AM/ }))
    expect(live.getByRole('heading', { level: 2, name: /^10:31 AM/ })).toHaveFocus()
    await userEvent.keyboard('{Escape}')
    expect(live.queryByRole('complementary')).toBeNull()
    expect(live.getByRole('button', { name: /^10:31 AM/ })).toHaveFocus()
  })

  it('shows the scoreboard whole, with its two plain lines', () => {
    render(<ConsoleSections />)
    const board = section('console-scoreboard')
    expect(board.getByRole('heading', { name: 'Eval scoreboard' })).toBeInTheDocument()
    expect(board.getByText(/^These figures come from recorded eval runs/)).toBeInTheDocument()
  })
})
