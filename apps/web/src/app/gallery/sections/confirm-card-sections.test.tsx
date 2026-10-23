import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithRouter } from '@/test/render-with-router'
import { ConfirmCardSections } from './confirm-card-sections'

// The browser tests address each state by its heading's id, so the ids are part of the contract.
const IDS = [
  'confirm-card-book-pending',
  'confirm-card-holiday-pending',
  'confirm-card-sick-pending',
  'confirm-card-approve-pending',
  'confirm-card-deny-pending',
  'confirm-card-cancel-pending',
  'confirm-card-short-notice-pending',
  'confirm-card-cross-year-sick-pending',
  'confirm-card-streaming',
  'confirm-card-confirming',
  'confirm-card-book-executed',
  'confirm-card-holiday-executed',
  'confirm-card-sick-executed',
  'confirm-card-approve-executed',
  'confirm-card-deny-executed-with-note',
  'confirm-card-deny-executed',
  'confirm-card-cancel-executed',
  'confirm-card-failed',
  'confirm-card-dismissed',
  'confirm-card-replaced',
  'confirm-card-expired',
]

const section = (id: string) => within(document.getElementById(id)!.closest('section')!)

describe('ConfirmCardSections', () => {
  it('has a heading with a stable id for every state, in page order', () => {
    const { container } = renderWithRouter(<ConfirmCardSections />)
    const found = [...container.querySelectorAll('h3[id]')]
      .map((heading) => heading.id)
      .filter((id) => /^[a-z][a-z0-9-]*$/.test(id))
    expect(found).toEqual(IDS)
  })

  it('does not take focus', () => {
    renderWithRouter(<ConfirmCardSections />)
    expect(document.body).toHaveFocus()
  })

  it('draws a pending card with the design’s figures', () => {
    renderWithRouter(<ConfirmCardSections />)
    const card = section('confirm-card-book-pending')
    expect(card.getByText('Expires at 3:42 PM')).toBeInTheDocument()
    expect(card.getByText(/84 hours \(10\.5 days\) left after this/)).toBeInTheDocument()
  })

  it('draws the streaming card with Confirm waiting, and the confirming card busy', () => {
    renderWithRouter(<ConfirmCardSections />)
    expect(
      section('confirm-card-streaming').getByRole('button', { name: /^Confirm/ }),
    ).toHaveAttribute('aria-disabled', 'true')
    expect(
      section('confirm-card-confirming').getByRole('button', { name: 'Confirming…' }),
    ).toHaveAttribute('aria-busy', 'true')
  })

  it('draws the deny card with a note, and the executed denials with and without one', () => {
    renderWithRouter(<ConfirmCardSections />)
    expect(
      section('confirm-card-deny-pending').getByRole('textbox', {
        name: 'Note to Zara (optional)',
      }),
    ).toHaveValue('Inventory runs November 9 and 10 this year. Could you move this a week later?')
    expect(section('confirm-card-deny-executed-with-note').getByRole('status')).toHaveTextContent(
      'Denied. Zara will see your note on the Time off page.',
    )
    expect(section('confirm-card-deny-executed').getByRole('status')).toHaveTextContent(
      'Denied. Zara will see it on the Time off page.',
    )
  })

  it('draws every ending with its line', () => {
    renderWithRouter(<ConfirmCardSections />)
    expect(
      section('confirm-card-failed').getByText(/^Couldn’t book this: you already/),
    ).toHaveTextContent(
      'Couldn’t book this: you already have time off on Friday, October 30. Nothing was changed.',
    )
    expect(section('confirm-card-dismissed').getByRole('status')).toHaveTextContent(
      'You dismissed this. Nothing was changed.',
    )
    expect(section('confirm-card-replaced').getByRole('status')).toHaveTextContent(
      'Replaced by a newer card. Nothing was changed.',
    )
    expect(
      section('confirm-card-expired').getByRole('button', { name: 'Ask again' }),
    ).toBeInTheDocument()
  })

  it('draws the cross-year sick card with a left line for each year', () => {
    renderWithRouter(<ConfirmCardSections />)
    const card = section('confirm-card-cross-year-sick-pending')
    expect(card.getByText('16 hours of sick leave left in 2026')).toBeInTheDocument()
    expect(card.getByText('32 hours of sick leave left in 2027')).toBeInTheDocument()
    expect(screen.getAllByRole('region', { name: 'Record sick time' }).length).toBeGreaterThan(1)
  })

  it('has only list items directly inside every list', () => {
    renderWithRouter(<ConfirmCardSections />)
    for (const list of document.querySelectorAll('ul, ol')) {
      for (const child of list.children) expect(child.tagName).toBe('LI')
    }
  })
})
