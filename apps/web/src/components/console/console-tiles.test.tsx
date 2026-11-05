import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ConsoleMetricsOut } from '@/api/generated'
import { ConsoleTiles } from './console-tiles'

const METRICS: ConsoleMetricsOut = {
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

const titles = (id: string) =>
  id === '4.1' ? 'Paid time off' : id === '5.2' ? 'Parental leave' : undefined
const tile = (name: string) => within(screen.getByRole('group', { name }))

describe('ConsoleTiles', () => {
  it('shows the eight tiles in order with the design’s copy', () => {
    render(<ConsoleTiles metrics={METRICS} sectionTitle={titles} />)
    const groups = screen.getAllByRole('group').map((g) => g.querySelector('h3')!.textContent)
    expect(groups).toEqual([
      'Time to first token',
      'Safety check time',
      'Cost per answered question',
      'Escalation rate',
      'Refusals and fallbacks',
      'Said the handbook doesn’t cover it',
      'Cards confirmed by a person',
      'Possible prompt injections',
    ])
    const first = tile('Time to first token')
    for (const t of [
      'Median',
      '1.6 s',
      '95th percentile 2.2 s',
      'Target 3 s',
      '9 turns · Small sample',
    ])
      expect(first.getByText(t)).toBeInTheDocument()
    const safety = tile('Safety check time')
    for (const t of ['95th percentile', '980 ms', 'Target 800 ms', '9 turns · Small sample'])
      expect(safety.getByText(t)).toBeInTheDocument()
    const cost = tile('Cost per answered question')
    for (const t of [
      '$0.021',
      '8 answered questions',
      'Sandbox spend $0.21 of $1.00 cap',
      'Small sample',
    ])
      expect(cost.getByText(t)).toBeInTheDocument()
    const esc = tile('Escalation rate')
    expect(esc.getByText('11%')).toBeInTheDocument()
    expect(esc.getByText('1 of 9 turns flagged by the safety check')).toBeInTheDocument()
    expect(tile('Refusals and fallbacks').getByText('0 of 9 turns')).toBeInTheDocument()
    const nf = tile('Said the handbook doesn’t cover it')
    expect(nf.getByText('of 9 turns')).toBeInTheDocument()
    expect(nf.getByText('None yet')).toBeInTheDocument()
    const cards = tile('Cards confirmed by a person')
    expect(cards.getByText('Time-off requests').closest('div')).toHaveTextContent(
      'Time-off requests1',
    )
    expect(cards.getByText('Decisions').closest('div')).toHaveTextContent('Decisions1')
    expect(cards.getByText('Cancellations').closest('div')).toHaveTextContent('Cancellations0')
    expect(cards.getByText('From the audit log')).toBeInTheDocument()
    expect(tile('Possible prompt injections').getByText('of 9 turns')).toBeInTheDocument()
  })

  it('lists the sections search came closest with, with their titles and counts', () => {
    const metrics = {
      ...METRICS,
      notFound: {
        count: 2,
        turns: 31,
        sections: [
          { sectionId: '4.1', count: 2 },
          { sectionId: '5.2', count: 1 },
          { sectionId: '9.9', count: 1 },
        ],
        smallSample: false,
      },
    }
    render(<ConsoleTiles metrics={metrics} sectionTitle={titles} />)
    const nf = tile('Said the handbook doesn’t cover it')
    expect(nf.getByText('4.1 Paid time off (2)')).toBeInTheDocument()
    expect(nf.getByText('5.2 Parental leave (1)')).toBeInTheDocument()
    expect(nf.getByText('9.9 (1)')).toBeInTheDocument()
    expect(nf.getByText('of 31 turns')).toBeInTheDocument()
    expect(nf.queryByText('Small sample')).not.toBeInTheDocument()
  })

  it('leaves out "Small sample" and the cost foot at 20 or more', () => {
    const metrics = {
      ...METRICS,
      firstToken: { ...METRICS.firstToken, sampleSize: 31, smallSample: false },
      cost: { ...METRICS.cost, smallSample: false },
    }
    render(<ConsoleTiles metrics={metrics} sectionTitle={titles} />)
    expect(tile('Time to first token').getByText('31 turns')).toBeInTheDocument()
    expect(tile('Cost per answered question').queryByText('Small sample')).not.toBeInTheDocument()
  })

  it('says "No turns yet" on every tile for a new sandbox, keeping the spend line', () => {
    const metrics: ConsoleMetricsOut = {
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
      cardsConfirmed: [],
      injections: { count: 0, turns: 0, smallSample: true },
    }
    render(<ConsoleTiles metrics={metrics} sectionTitle={titles} />)
    expect(screen.getAllByText('No turns yet')).toHaveLength(8)
    expect(
      tile('Cost per answered question').getByText('Sandbox spend $0.00 of $1.00 cap'),
    ).toBeInTheDocument()
  })

  it('always lists the three card rows, with 0 for an action the audit log has no row for', () => {
    render(<ConsoleTiles metrics={{ ...METRICS, cardsConfirmed: [] }} sectionTitle={titles} />)
    const cards = tile('Cards confirmed by a person')
    expect(cards.getByText('Time-off requests').closest('div')).toHaveTextContent(
      'Time-off requests0',
    )
    expect(cards.getByText('Decisions').closest('div')).toHaveTextContent('Decisions0')
    expect(cards.getByText('Cancellations').closest('div')).toHaveTextContent('Cancellations0')
  })

  it('shows eight loading tiles with their titles and no figures', () => {
    render(<ConsoleTiles loading sectionTitle={titles} />)
    expect(screen.getAllByRole('group')).toHaveLength(8)
    expect(screen.queryByText(/\d/)).not.toBeInTheDocument()
  })

  it('lays the tiles out as auto-fill columns, one per row at a phone', () => {
    const { container } = render(<ConsoleTiles metrics={METRICS} sectionTitle={titles} />)
    expect(container.firstElementChild).toHaveClass(
      'grid-cols-[repeat(auto-fill,minmax(220px,1fr))]',
      'gap-4',
    )
  })
})
