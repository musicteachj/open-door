import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { CaseSummaryBlock } from './case-summary-block'

const TEXT =
  'The person says their manager keeps making comments.\nThey say see https://example.com and **bold**.'

function written(extra = {}) {
  return render(
    <CaseSummaryBlock
      state="written"
      text={TEXT}
      writtenAt="2026-10-26T16:41:00Z"
      model="claude-opus-5-5"
      timeZone="America/Denver"
      {...extra}
    />,
  )
}

describe('CaseSummaryBlock', () => {
  it('is a section labeled "AI summary" with the AI tag', () => {
    written()
    const section = screen.getByRole('region', { name: 'AI summary' })
    expect(section).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'AI summary' })).toBeInTheDocument()
    expect(screen.getByText('AI')).toHaveAttribute('aria-hidden', 'true')
    expect(section).not.toHaveAttribute('aria-busy')
  })

  it('shows the text as plain text: whitespace kept, nothing linkified or rendered as Markdown', () => {
    const { container } = written()
    const text = screen.getByText(/The person says/)
    expect(text.textContent).toBe(TEXT)
    expect(text).toHaveClass('whitespace-pre-wrap')
    expect(container.querySelector('a')).toBeNull()
    expect(container.querySelector('strong, em, code')).toBeNull()
  })

  it('says who wrote it, when, and with which model', () => {
    written()
    expect(
      screen.getByText(
        'Written by Open Door’s AI to be neutral, with no recommendation · Mon, Oct 26, 10:41 AM MDT ·',
        { exact: false },
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('Claude Opus 5.5')).toBeInTheDocument()
  })

  it('falls back to the raw model id', () => {
    written({ model: 'mystery-model' })
    expect(screen.getByText('mystery-model')).toBeInTheDocument()
  })

  it('leaves out a missing time or model without a dangling dot', () => {
    const { rerender } = written({ model: undefined })
    const meta = () => document.querySelector('p.text-small')!.textContent
    expect(meta()).toBe(
      'Written by Open Door’s AI to be neutral, with no recommendation · Mon, Oct 26, 10:41 AM MDT',
    )
    rerender(<CaseSummaryBlock state="written" text="x" model="claude-opus-5-5" />)
    expect(meta()).toBe(
      'Written by Open Door’s AI to be neutral, with no recommendation · Claude Opus 5.5',
    )
    rerender(<CaseSummaryBlock state="written" text="x" />)
    expect(meta()).toBe('Written by Open Door’s AI to be neutral, with no recommendation')
  })

  it('pending: a status line, aria-busy, and three static bars', () => {
    render(<CaseSummaryBlock state="pending" />)
    expect(screen.getByRole('region', { name: 'AI summary' })).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('status')).toHaveTextContent('Writing the summary…')
    const bars = document.querySelectorAll('[data-slot="skeleton"]')
    expect(bars).toHaveLength(3)
    for (const bar of bars) expect(bar.className).not.toMatch(/animate/)
  })

  it('failed: the line and a secondary Try again that calls onRetry', async () => {
    const onRetry = vi.fn<() => void>()
    render(<CaseSummaryBlock state="failed" onRetry={onRetry} />)
    expect(screen.getByText('No AI summary. Read the person’s words below.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('failed: no Try again when retrying is not allowed (a closed case)', () => {
    render(<CaseSummaryBlock state="failed" onRetry={() => {}} canRetry={false} />)
    expect(screen.getByText('No AI summary. Read the person’s words below.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull()
  })

  it('failed: Try again is busy and does nothing while retrying', async () => {
    const onRetry = vi.fn<() => void>()
    render(<CaseSummaryBlock state="failed" onRetry={onRetry} retrying />)
    const button = screen.getByRole('button', { name: 'Try again' })
    expect(button).toHaveAttribute('aria-busy', 'true')
    await userEvent.click(button)
    expect(onRetry).not.toHaveBeenCalled()
  })

  it('crisis: the fact, and no Try again', () => {
    render(<CaseSummaryBlock state="crisis" />)
    expect(
      screen.getByText('No AI summary for this case. The safety check routed it to crisis text.'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('merges a className over its own classes', () => {
    render(<CaseSummaryBlock state="crisis" className="rounded-none" />)
    const section = screen.getByRole('region', { name: 'AI summary' })
    expect(section).toHaveClass('rounded-none')
    expect(section).not.toHaveClass('rounded-lg')
  })

  it('has no pronouns and no red', () => {
    const { container } = render(<CaseSummaryBlock state="failed" onRetry={() => {}} />)
    expect(container.innerHTML).not.toMatch(/danger/)
  })
})
