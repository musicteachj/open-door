import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { CaseWordsReveal } from './case-words-reveal'

const WORDS = 'My manager said:\n  see https://example.com **now**'

describe('CaseWordsReveal', () => {
  it('hidden: says so, and offers Show with an expanded=false disclosure', () => {
    render(<CaseWordsReveal firstName="Priya" state="hidden" />)
    expect(screen.getByRole('heading', { level: 2, name: 'Priya’s words' })).toBeInTheDocument()
    expect(
      screen.getByText(
        'Priya’s words are hidden. Opening them is recorded in this case’s timeline.',
      ),
    ).toBeInTheDocument()
    const button = screen.getByRole('button', { name: 'Show Priya’s words' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    const body = document.getElementById(button.getAttribute('aria-controls')!)
    expect(body).toBeInTheDocument()
    expect(body).toBeEmptyDOMElement()
  })

  it('calls onShow when Show is pressed, and keeps focus on the button', async () => {
    const onShow = vi.fn<() => void>()
    render(<CaseWordsReveal firstName="Priya" state="hidden" onShow={onShow} />)
    const button = screen.getByRole('button', { name: 'Show Priya’s words' })
    await userEvent.click(button)
    expect(onShow).toHaveBeenCalledTimes(1)
    expect(button).toHaveFocus()
  })

  it('shown: the words as plain text in the controlled container, with Hide', async () => {
    const onHide = vi.fn<() => void>()
    const { container } = render(
      <CaseWordsReveal firstName="Priya" state="shown" words={WORDS} onHide={onHide} />,
    )
    const button = screen.getByRole('button', { name: 'Hide Priya’s words' })
    expect(button).toHaveAttribute('aria-expanded', 'true')
    const body = document.getElementById(button.getAttribute('aria-controls')!)!
    const text = screen.getByText(/My manager said/)
    expect(body).toContainElement(text)
    expect(text.textContent).toBe(WORDS)
    expect(text).toHaveClass('whitespace-pre-wrap')
    expect(container.querySelector('a, strong, em')).toBeNull()
    expect(screen.queryByText(/are hidden/)).toBeNull()
    await userEvent.click(button)
    expect(onHide).toHaveBeenCalledTimes(1)
  })

  it('loading: the button is busy and does nothing; the words are not there', async () => {
    const onShow = vi.fn<() => void>()
    render(<CaseWordsReveal firstName="Priya" state="loading" onShow={onShow} />)
    const button = screen.getByRole('button', { name: 'Show Priya’s words' })
    expect(button).toHaveAttribute('aria-busy', 'true')
    expect(button).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(button)
    expect(onShow).not.toHaveBeenCalled()
  })

  it('failed: an error line and Try again, which shows the words again', async () => {
    const onShow = vi.fn<() => void>()
    render(<CaseWordsReveal firstName="Priya" state="failed" onShow={onShow} />)
    expect(
      screen.getByText('Priya’s words couldn’t be opened. Please try again.'),
    ).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onShow).toHaveBeenCalledTimes(1)
  })

  it('failed: the error line is an alert, and Try again is not a disclosure', () => {
    render(<CaseWordsReveal firstName="Priya" state="failed" />)
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Priya’s words couldn’t be opened. Please try again.',
    )
    const retry = screen.getByRole('button', { name: 'Try again' })
    expect(retry).not.toHaveAttribute('aria-expanded')
    expect(retry).not.toHaveAttribute('aria-controls')
  })

  it('has no alert unless it failed', () => {
    render(<CaseWordsReveal firstName="Priya" state="hidden" />)
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('merges a className over its own classes', () => {
    const { container } = render(
      <CaseWordsReveal firstName="Priya" state="hidden" className="px-4" />,
    )
    const section = container.querySelector('section')!
    expect(section).toHaveClass('px-4')
    expect(section).not.toHaveClass('px-6')
  })

  it('sits on the confidential tint with the lock in primary', () => {
    const { container } = render(<CaseWordsReveal firstName="Priya" state="hidden" />)
    const section = container.querySelector('section')!
    expect(section).toHaveClass('bg-confidential-tint', 'border-confidential-border')
    expect(section.querySelector('h2 svg')).toHaveClass('text-primary')
  })
})
