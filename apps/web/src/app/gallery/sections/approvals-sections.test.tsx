import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { renderWithRouter } from '@/test/render-with-router'
import { ApprovalsSections } from './approvals-sections'

// The browser tests address each state by its heading's id, so the ids are part of the contract.
const IDS = [
  'approval-card-default',
  'approval-card-no-coverage',
  'approval-card-conflict',
  'approval-card-conflict-decided',
  'approval-card-loading',
  'coverage-line-one-person',
  'coverage-line-none',
  'coverage-line-range',
  'coverage-line-part-of-day',
  'note-field-empty',
  'note-field-typed',
  'note-field-at-limit',
  'note-field-disabled',
  'decision-dialog-approve',
  'decision-dialog-deny',
  'decision-dialog-deciding',
]

const section = (id: string) => within(document.getElementById(id)!.closest('section')!)

describe('ApprovalsSections', () => {
  it('has a heading with a stable id for every state, in page order', () => {
    const { container } = renderWithRouter(<ApprovalsSections />)
    const found = [...container.querySelectorAll('h3[id]')]
      .map((heading) => heading.id)
      .filter((id) => /^[a-z][a-z0-9-]*$/.test(id))
    expect(found).toEqual(IDS)
  })

  it('does not take focus, so the page keeps its own first Tab target', () => {
    renderWithRouter(<ApprovalsSections />)
    expect(document.body).toHaveFocus()
  })

  it('draws the dialogs closed, behind buttons', () => {
    renderWithRouter(<ApprovalsSections />)
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    for (const name of [
      'Open the approve dialog',
      'Open the deny dialog',
      'Open the deciding dialog',
    ]) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument()
    }
  })

  it('opens the approve dialog from its button, with focus on Go back', async () => {
    const user = userEvent.setup()
    renderWithRouter(<ApprovalsSections />)
    await user.click(screen.getByRole('button', { name: 'Open the approve dialog' }))
    expect(
      screen.getByRole('alertdialog', { name: 'Approve Zara Bautista’s PTO?' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Go back' })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'Go back' }))
    expect(screen.getByRole('button', { name: 'Open the approve dialog' })).toHaveFocus()
  })

  it('opens the deny dialog with the typed note and focus in it', async () => {
    const user = userEvent.setup()
    renderWithRouter(<ApprovalsSections />)
    await user.click(screen.getByRole('button', { name: 'Open the deny dialog' }))
    expect(screen.getByRole('textbox', { name: 'Note to Zara (optional)' })).toHaveFocus()
    expect(within(screen.getByRole('alertdialog')).getByText('77 of 300')).toBeInTheDocument()
  })

  it('draws the approval cards from the design’s figures', () => {
    renderWithRouter(<ApprovalsSections />)
    const card = section('approval-card-default')
    expect(card.getByText('62 hours (7.75 days) available after this')).toBeInTheDocument()
    expect(
      card.getByText('Also off: Vikram Morales, Tuesday, November 10 · PTO'),
    ).toBeInTheDocument()
    expect(
      section('approval-card-no-coverage').getByText('84 hours (10.5 days) available after this'),
    ).toBeInTheDocument()
    expect(
      section('approval-card-conflict').getByText('Zara canceled this request.'),
    ).toBeInTheDocument()
  })

  it('draws the note field at its limit', () => {
    renderWithRouter(<ApprovalsSections />)
    expect(section('note-field-at-limit').getByText('300 of 300')).toBeInTheDocument()
    expect(section('note-field-disabled').getByRole('textbox')).toBeDisabled()
  })

  it('has only list items directly inside every list', () => {
    renderWithRouter(<ApprovalsSections />)
    for (const list of document.querySelectorAll('ul, ol')) {
      for (const child of list.children) expect(child.tagName).toBe('LI')
    }
  })
})
