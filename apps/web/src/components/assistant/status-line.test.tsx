import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { StatusLine } from './status-line'

const steps = [
  { id: 'a', text: 'Searched the handbook: sick leave', done: true },
  { id: 'b', text: 'Searching the handbook again…', done: false },
]

describe('StatusLine', () => {
  it('is a polite live region', () => {
    render(<StatusLine steps={steps} />)
    const region = screen.getByRole('status')
    expect(region).toHaveAttribute('aria-live', 'polite')
  })

  it('lists each step in order, with the API text as given', () => {
    render(<StatusLine steps={steps} />)
    const items = within(screen.getByRole('status')).getAllByRole('listitem')
    expect(items.map((item) => item.textContent)).toEqual([
      'Searched the handbook: sick leave',
      'Searching the handbook again…',
    ])
  })

  it('gives a finished step a check in muted ink', () => {
    render(<StatusLine steps={steps} />)
    const done = screen.getByText('Searched the handbook: sick leave')
    expect(done.querySelector('[data-slot="status-check"]')).toHaveAttribute('aria-hidden', 'true')
    expect(done.querySelector('[data-slot="status-spinner"]')).toBeNull()
    expect(done).toHaveClass('text-ink-muted')
  })

  it('gives the current step a spinner in full ink', () => {
    render(<StatusLine steps={steps} />)
    const current = screen.getByText('Searching the handbook again…')
    const spinner = current.querySelector('[data-slot="status-spinner"]')
    expect(spinner).toHaveAttribute('aria-hidden', 'true')
    expect(spinner).toHaveClass('animate-spin')
    expect(current.querySelector('[data-slot="status-check"]')).toBeNull()
    expect(current).toHaveClass('text-ink')
  })

  it('shows one current step alone, as before any text arrives', () => {
    render(<StatusLine steps={[{ id: 'a', text: 'Searching the handbook…', done: false }]} />)
    expect(screen.getAllByRole('listitem')).toHaveLength(1)
    expect(screen.getByText('Searching the handbook…')).toBeInTheDocument()
  })

  it('is an empty polite status with no steps, so the region is in the page before the first step', () => {
    render(<StatusLine steps={[]} />)
    const region = screen.getByRole('status')
    expect(region).toBeEmptyDOMElement()
    expect(region).toHaveAttribute('aria-live', 'polite')
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('is not atomic, so a screen reader says the step that changed and not the whole list again', () => {
    render(<StatusLine steps={[{ id: 'a', text: 'Searching the handbook…', done: false }]} />)
    expect(screen.getByRole('status')).toHaveAttribute('aria-atomic', 'false')
  })

  it('takes no room while it is empty, and the same region then holds the first step', () => {
    const { rerender } = render(<StatusLine steps={[]} />)
    const region = screen.getByRole('status')
    expect(region).toHaveClass('empty:-mt-3.5')
    rerender(<StatusLine steps={[{ id: 'a', text: 'Searching the handbook…', done: false }]} />)
    expect(screen.getByRole('status')).toBe(region)
    expect(region).toHaveTextContent('Searching the handbook…')
  })
})

describe('StatusLine with a repeated step ID', () => {
  it('draws no React key warning, and shows both steps', () => {
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <StatusLine
        steps={[
          { id: 'tool-1', text: 'Searched the handbook', done: true },
          { id: 'tool-1', text: 'Searching the handbook again…', done: false },
        ]}
      />,
    )
    expect(screen.getByText('Searched the handbook')).toBeInTheDocument()
    expect(screen.getByText('Searching the handbook again…')).toBeInTheDocument()
    const reported = errors.mock.calls.map((call) => String(call[0]) + String(call[1] ?? ''))
    expect(reported.filter((text) => /same key/.test(text))).toEqual([])
    errors.mockRestore()
  })
})
