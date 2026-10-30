import { render, screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/render-with-router'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { BudgetBanner } from './budget-banner'

const SANDBOX_TEXT =
  'This demo sandbox has reached its limit for the assistant. A new sandbox starts fresh. If you or someone else is in danger, call 911, or call or text 988 to reach the 988 Suicide & Crisis Lifeline.'
const DAILY_TEXT =
  "Today's demo budget for the assistant is used up. It's available again tomorrow. If you or someone else is in danger, call 911, or call or text 988 to reach the 988 Suicide & Crisis Lifeline."

describe('BudgetBanner: the 911 and 988 calls', () => {
  it.each([
    ['sandbox', SANDBOX_TEXT],
    ['daily', DAILY_TEXT],
  ] as const)('links 911 and 988 in the %s text, with its words unchanged', (kind, text) => {
    render(<BudgetBanner kind={kind} message={text} />)
    const status = screen.getByRole('status')
    expect(status).toHaveTextContent(text)
    expect(status.querySelector('p')!.textContent).toBe(text)
    expect(screen.getByRole('link', { name: 'call 911' })).toHaveAttribute('href', 'tel:911')
    expect(screen.getByRole('link', { name: 'call or text 988' })).toHaveAttribute(
      'href',
      'tel:988',
    )
    expect(screen.getAllByRole('link')).toHaveLength(2)
  })
})

describe('BudgetBanner', () => {
  it('shows the sandbox text from the API as a polite status, with the warning icon', () => {
    render(<BudgetBanner kind="sandbox" message={SANDBOX_TEXT} onStartNewSandbox={() => {}} />)
    const status = screen.getByRole('status')
    expect(status).toHaveTextContent(SANDBOX_TEXT)
    expect(status.querySelector('[data-slot="banner-icon"]')).toHaveClass('text-warning')
  })

  it('offers "Start a new sandbox" on the sandbox banner, and calls the handler', async () => {
    const onStartNewSandbox = vi.fn<() => void>()
    render(
      <BudgetBanner kind="sandbox" message={SANDBOX_TEXT} onStartNewSandbox={onStartNewSandbox} />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Start a new sandbox' }))
    expect(onStartNewSandbox).toHaveBeenCalledTimes(1)
  })

  it('has no button on the sandbox banner without a handler', () => {
    render(<BudgetBanner kind="sandbox" message={SANDBOX_TEXT} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('shows the daily text, with no button even if a handler is passed', () => {
    render(<BudgetBanner kind="daily" message={DAILY_TEXT} onStartNewSandbox={() => {}} />)
    expect(screen.getByRole('status')).toHaveTextContent(DAILY_TEXT)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('cannot be dismissed: the composer stays off until the budget is back', () => {
    render(<BudgetBanner kind="daily" message={DAILY_TEXT} />)
    expect(screen.queryByRole('button', { name: /dismiss/i })).not.toBeInTheDocument()
  })
})

describe('BudgetBanner: Write to HR', () => {
  it('shows the link inside the text, after it, when given one', () => {
    renderWithRouter(
      <BudgetBanner
        kind="daily"
        message={DAILY_TEXT}
        writeToHr={{ to: '/my-cases', label: 'Write to HR' }}
      />,
    )
    const link = screen.getByRole('link', { name: 'Write to HR' })
    expect(link).toHaveAttribute('href', '/my-cases')
    expect(link.closest('p')).toHaveTextContent(`${DAILY_TEXT} Write to HR`)
  })

  it('shows no link when given null, or nothing', () => {
    renderWithRouter(<BudgetBanner kind="daily" message={DAILY_TEXT} writeToHr={null} />)
    expect(screen.queryByRole('link', { name: 'Write to HR' })).not.toBeInTheDocument()
  })
})
