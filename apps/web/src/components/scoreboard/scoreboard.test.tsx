import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import generated from '@/generated/scoreboard.json'
import { Scoreboard } from './scoreboard'
import { isScoreboard, type ScoreboardData } from './types'

if (!isScoreboard(generated)) throw new Error('The generated scoreboard has an unexpected shape.')
const DATA: ScoreboardData = generated

describe('Scoreboard', () => {
  it('has an h2 "Eval scoreboard" and can change its level', () => {
    const { rerender } = render(<Scoreboard data={DATA} />)
    expect(screen.getByRole('heading', { level: 2, name: 'Eval scoreboard' })).toBeInTheDocument()
    rerender(<Scoreboard data={DATA} headingLevel={3} />)
    expect(screen.getByRole('heading', { level: 3, name: 'Eval scoreboard' })).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { level: 4, name: 'History of full runs' }),
    ).toBeInTheDocument()
  })

  it('names the models from the Q&A set, in mono', () => {
    render(<Scoreboard data={DATA} />)
    const line = screen.getByText(/^Assistant/).closest('p')!
    expect(line).toHaveTextContent(
      'Assistant claude-opus-5-5 · safety check claude-haiku-5-5 · judge claude-sonnet-5-5',
    )
    expect(within(line).getByText('claude-haiku-5-5').tagName).toBe('CODE')
    expect(screen.getByText('Three trials per set unless noted.')).toBeInTheDocument()
  })

  it('leaves the models line out when no set has them', () => {
    const data = { ...DATA, sets: DATA.sets.map((s) => ({ ...s, facts: null })) }
    render(<Scoreboard data={data} />)
    expect(screen.queryByText(/^Assistant/)).toBeNull()
  })

  it('shows every set in a table with a caption, its headline, lowest trial, and other figures', () => {
    render(<Scoreboard data={DATA} />)
    const table = screen.getByRole('table', { name: 'Eval sets' })
    expect(within(table).getAllByRole('row')).toHaveLength(DATA.sets.length + 1)
    expect(
      within(table)
        .getAllByRole('columnheader')
        .map((h) => h.textContent),
    ).toEqual(['Set', 'Result', 'Lowest trial', 'Other figures'])
    const qa = within(
      within(table)
        .getByRole('rowheader', { name: /Policy Q&A/ })
        .closest('tr')!,
    )
    expect(qa.getByText('Full run, Nov 3, 2026')).toBeInTheDocument()
    expect(qa.getByText('99%')).toBeInTheDocument()
    expect(qa.getByText('Program checks')).toBeInTheDocument()
    expect(qa.getByText('97%')).toBeInTheDocument()
    expect(qa.getByText('Unanswerable 97%, lowest 90%')).toBeInTheDocument()
  })

  it('shows each other figure on its own line', () => {
    render(<Scoreboard data={DATA} />)
    const quality = within(screen.getByRole('rowheader', { name: /Answer quality/ }).closest('tr')!)
    for (const line of [
      'Target 85%',
      '16.3 uncited claims',
      'Judge agreement with the hand grades 91.2%',
    ])
      expect(quality.getByText(line)).toBeInTheDocument()
  })

  it('says why a set has no lowest trial, in muted ink', () => {
    render(<Scoreboard data={DATA} />)
    expect(screen.getByText('No trials: retrieval is exact.')).toHaveClass('text-ink-muted')
  })

  it('spans a set that was not run, saying so', () => {
    const data: ScoreboardData = {
      ...DATA,
      sets: [
        ...DATA.sets,
        {
          key: 'x',
          name: 'Fairness',
          detail: null,
          notRun: true,
          headline: null,
          lowest: null,
          also: [],
          facts: null,
        },
      ],
    }
    render(<Scoreboard data={data} />)
    const cell = screen.getByText('Not measured yet.')
    expect(screen.queryByText(/Phase 7/)).toBeNull()
    expect(cell).toHaveAttribute('colspan', '3')
    expect(cell).toHaveClass('text-ink-muted')
  })

  it('shows a set that ran but has no headline as not measured yet, and a missing lowest as a dash', () => {
    const ran = {
      key: 'x',
      name: 'Fairness',
      detail: 'Full run, Nov 3, 2026',
      notRun: false,
      also: [],
      facts: null,
    }
    const data: ScoreboardData = {
      ...DATA,
      sets: [
        { ...ran, headline: null, lowest: { value: 0.9, display: '90%' } },
        {
          ...ran,
          key: 'y',
          name: 'Other',
          headline: { label: 'Passed', value: 0.95, display: '95%' },
          lowest: null,
        },
      ],
    }
    render(<Scoreboard data={data} />)
    expect(screen.getByText('Not measured yet.')).toHaveClass('text-ink-muted')
    const other = within(screen.getByRole('table', { name: 'Eval sets' })).getByRole('row', {
      name: /^Other/,
    })
    expect(within(other).getByText('95%')).toBeInTheDocument()
    // The lowest trial and the other figures are both empty here.
    const nones = within(other).getAllByText('None')
    expect(nones).toHaveLength(2)
    expect(nones[0]).toHaveClass('sr-only')
    expect(within(other).getAllByText('–', { selector: '[aria-hidden="true"]' })).toHaveLength(2)
  })

  it('shows the history newest first, with the model by its display name', () => {
    render(<Scoreboard data={DATA} />)
    const table = screen.getByRole('table', { name: 'History of full runs' })
    expect(
      within(table)
        .getAllByRole('columnheader')
        .map((h) => h.textContent),
    ).toEqual(['Date', 'Model', 'Q&A', 'Unanswerable', 'Red team', 'Actions', 'Judge', 'Cost'])
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(DATA.history.length)
    expect(rows[0]).toHaveTextContent('Nov 3, 2026, 18:45 UTC')
    expect(rows[0]).toHaveTextContent('Claude Sonnet 5.5')
    expect(rows[0]).toHaveTextContent('$9.44')
    expect(rows[rows.length - 1]).toHaveTextContent('Oct 19, 2026, 15:22 UTC')
  })

  it('shows a missing history figure as a dash with a hidden "Not in the set"', () => {
    render(<Scoreboard data={DATA} />)
    const oldest = screen.getAllByRole('row').find((r) => r.textContent?.includes('Oct 19, 2026'))!
    expect(within(oldest).getByText('Not in the set')).toHaveClass('sr-only')
  })

  it('says when Actions joined the full set, from the first run that has it', () => {
    render(<Scoreboard data={DATA} />)
    expect(screen.getByText('Actions joined the full set on Oct 25, 2026.')).toBeInTheDocument()
  })

  it('uses a date with no comma whole in the Actions footnote', () => {
    const [first, second, ...rest] = DATA.history
    const data = {
      ...DATA,
      history: [
        { ...first!, actions: null },
        { ...second!, actions: '90%', date: 'Oct 25' },
        ...rest,
      ],
    }
    render(<Scoreboard data={data} />)
    expect(screen.getByText('Actions joined the full set on Oct 25.')).toBeInTheDocument()
  })

  it('leaves the footnote out when the first run already had Actions', () => {
    const data = { ...DATA, history: DATA.history.slice(1) }
    render(<Scoreboard data={data} />)
    expect(screen.queryByText(/Actions joined/)).toBeNull()
  })

  it('always shows the two plain lines, with the item count from the data', () => {
    render(<Scoreboard data={DATA} />)
    expect(
      screen.getByText(
        "These figures come from recorded eval runs. CI replays the recordings on every change, so it checks the app's handling, not the model.",
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        'The sets are small (206 items in the full set), so a single item can move a figure by more than a point.',
      ),
    ).toBeInTheDocument()
  })

  it('does not hard-code the item count', () => {
    const data = {
      ...DATA,
      sets: DATA.sets.map((s) =>
        s.key === 'qa' ? { ...s, facts: { ...s.facts, itemsPerTrial: 120 } } : s,
      ),
    }
    render(<Scoreboard data={data} />)
    expect(screen.getByText(/120 items in the full set/)).toBeInTheDocument()
  })

  it('scrolls each table inside its own keyboard-focusable, labeled region at 640 px minimum', () => {
    render(<Scoreboard data={DATA} />)
    for (const name of ['Eval sets', 'History of full runs']) {
      const region = screen.getByRole('region', { name })
      expect(region).toHaveAttribute('tabindex', '0')
      expect(region).toHaveClass('overflow-x-auto')
      expect(within(region).getByRole('table')).toHaveClass('min-w-160')
    }
  })

  it('has no link and no color on a figure', () => {
    const { container } = render(<Scoreboard data={DATA} />)
    expect(container.querySelector('a')).toBeNull()
    expect(container.innerHTML).not.toMatch(/danger|warning|success|marker/)
  })
})
