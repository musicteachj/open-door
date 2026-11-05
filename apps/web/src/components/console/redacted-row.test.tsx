import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { T_ABANDONED, T_FLAGGED } from '@/app/gallery/fixtures/console'
import { RedactedRow } from './redacted-row'

describe('RedactedRow', () => {
  it('says a flagged turn was flagged and gives its facts', () => {
    render(<RedactedRow turn={T_FLAGGED} />)
    expect(
      screen.getByText('Flagged by the safety check. Details are hidden to protect the person.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        'Oct 26 · 14,800 input tokens · 550 output · $0.024 · safety check 760 ms · first token 1.9 s · total 5.2 s',
      ),
    ).toBeInTheDocument()
  })

  it('says an abandoned turn did not finish, and never says it was flagged', () => {
    const { container } = render(<RedactedRow turn={T_ABANDONED} />)
    expect(
      screen.getByText(
        'This turn didn’t finish, so its safety check result wasn’t kept. Details are hidden to protect the person.',
      ),
    ).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/flagged/i)
    // Its null timings are dropped, not shown as blanks.
    expect(screen.getByText('Oct 26 · 5,200 input tokens · 0 output · $0.004')).toBeInTheDocument()
  })

  it('is the tour’s target only when the turn was flagged, never when it was abandoned', () => {
    const flagged = render(<RedactedRow turn={T_FLAGGED} />)
    expect(flagged.container.querySelector('[data-tour="flagged-row"]')).not.toBeNull()
    const abandoned = render(<RedactedRow turn={T_ABANDONED} />)
    expect(abandoned.container.querySelector('[data-tour]')).toBeNull()
  })

  it('is one plain cell: no button, nothing focusable', () => {
    const { container } = render(<RedactedRow turn={T_FLAGGED} />)
    expect(screen.getAllByRole('cell')).toHaveLength(1)
    expect(container.querySelector('button, a, [tabindex]')).toBeNull()
  })

  it('draws a lock in primary on the confidential tint', () => {
    const { container } = render(<RedactedRow turn={T_FLAGGED} />)
    expect(screen.getByRole('cell')).toHaveClass('bg-confidential-tint')
    const lock = container.querySelector('svg')
    expect(lock).toHaveAttribute('aria-hidden', 'true')
    expect(lock).toHaveClass('text-primary')
  })
})
