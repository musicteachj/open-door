import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithRouter } from '@/test/render-with-router'
import { TimeOffSections } from './timeoff-sections'

// The browser tests address each state by its heading's id, so the ids are part of the contract.
const IDS = [
  'status-badge-waiting',
  'status-badge-approved',
  'status-badge-denied',
  'status-badge-recorded',
  'status-badge-canceled',
  'segmented-control-default',
  'segmented-control-selected',
  'segmented-control-disabled',
  'choice-group-default',
  'choice-group-selected',
  'choice-group-disabled',
  'hours-stepper-default',
  'hours-stepper-at-1',
  'hours-stepper-at-8',
  'hours-stepper-error',
  'hours-stepper-disabled',
  'date-field-empty',
  'date-field-one-day',
  'date-field-range',
  'date-field-open',
  'date-field-error',
  'date-field-disabled',
  'date-picker-pto',
  'date-picker-sick',
  'date-picker-range',
  'form-message-warning',
  'form-message-refusal',
  'alert-dialog-cancel-request',
  'balance-card-pto',
  'balance-card-ceiling',
  'balance-card-sick',
  'balance-card-empty',
  'balance-card-loading',
  'request-row-approved',
  'request-row-waiting',
  'request-row-recorded',
  'request-row-canceled',
  'request-row-denied',
  'request-row-team',
  'request-row-team-denied',
  'request-group-upcoming',
  'request-group-empty',
  'preview-block-one-day',
  'preview-block-weekend',
  'preview-block-holiday',
  'preview-block-sick-hours',
  'preview-block-already-booked',
  'preview-block-runs',
  'preview-block-cross-year-sick',
  'preview-block-nothing-picked',
  'preview-block-nothing-counted',
  'request-form-pto-one-day',
  'request-form-holiday-range',
  'request-form-sick-hours',
  'request-form-short-notice',
  'request-form-not-enough',
  'request-form-overlap',
  'request-form-submitting',
  'request-form-sheet',
]

describe('TimeOffSections', () => {
  it('has a heading with a stable id for every state', () => {
    const { container } = renderWithRouter(<TimeOffSections />)
    const missing = IDS.filter((id) => container.querySelector(`h3#${id}`) === null)
    expect(missing).toEqual([])
  })

  it('has no state that is not on the list, so the list stays the page order', () => {
    const { container } = renderWithRouter(<TimeOffSections />)
    // A component's own heading carries a generated id (`_r_1_`); the gallery's are kebab-case.
    const found = [...container.querySelectorAll('h3[id]')]
      .map((heading) => heading.id)
      .filter((id) => /^[a-z][a-z0-9-]*$/.test(id))
    expect(found).toEqual(IDS)
  })

  it('does not take focus, so the page keeps its own first Tab target', () => {
    renderWithRouter(<TimeOffSections />)
    expect(document.body).toHaveFocus()
  })

  it('draws the alert dialog closed, behind a button', () => {
    renderWithRouter(<TimeOffSections />)
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel time off' })).toBeInTheDocument()
  })

  it('draws the PTO and sick pickers for October 2026, and the range picker for November', () => {
    renderWithRouter(<TimeOffSections />)
    const grids = screen.getAllByRole('grid').map((grid) => grid.getAttribute('aria-labelledby'))
    // The three picker states, and none inside the request forms: they start with it closed.
    expect(grids).toHaveLength(3)
    expect(screen.getAllByText('October 2026')).toHaveLength(2)
    expect(screen.getByText('November 2026')).toBeInTheDocument()
    expect(screen.getByText('Sick time can go back 30 days, to September 20')).toBeInTheDocument()
  })

  it('shows the two form messages with their roles', () => {
    renderWithRouter(<TimeOffSections />)
    const inSection = (id: string) => within(document.getElementById(id)!.closest('section')!)
    expect(
      inSection('form-message-warning').getByText(
        'More than 3 days usually needs 2 weeks’ notice. You can still request it.',
      ),
    ).toBeInTheDocument()
    expect(
      inSection('form-message-refusal').getByText(
        'You have 92 hours (11.5 days) available. This request needs 120 hours (15 days).',
      ),
    ).toBeInTheDocument()
  })

  it('draws the balance cards with the design’s figures', () => {
    renderWithRouter(<TimeOffSections />)
    const section = (id: string) => document.getElementById(id)!.closest('section')!
    expect(section('balance-card-pto')).toHaveTextContent('92 hours11.5 days')
    expect(section('balance-card-ceiling')).toHaveTextContent('172 hours21.5 days')
    expect(section('balance-card-ceiling')).toHaveTextContent('Next: paused at the 180-hour limit')
    expect(section('balance-card-sick')).toHaveTextContent('32 hours')
    expect(section('balance-card-empty')).toHaveTextContent('132 hours16.5 days')
  })

  it('draws the request form closed over its picker, in a docked frame', () => {
    renderWithRouter(<TimeOffSections />)
    expect(screen.getAllByRole('region', { name: 'Request time off' })).toHaveLength(7)
    expect(screen.getByRole('button', { name: 'Requesting…' })).toHaveAttribute('aria-busy', 'true')
  })

  it('shows every figure in a state as the API label it was given', () => {
    renderWithRouter(<TimeOffSections />)
    expect(screen.getByText('16 hours of sick leave left in 2026')).toBeInTheDocument()
    expect(screen.getByText('32 hours of sick leave left in 2027')).toBeInTheDocument()
    expect(
      screen.getByText('Saturdays and Sundays in these dates aren’t on your schedule'),
    ).toBeInTheDocument()
  })

  it('lets the pair of empty balance cards shrink to a phone, so the page never scrolls sideways', () => {
    renderWithRouter(<TimeOffSections />)
    const pair = document
      .getElementById('balance-card-empty')!
      .closest('section')!
      .querySelector('.flex-wrap .flex-wrap')!
    expect(pair).toHaveClass('w-full', 'min-w-0')
  })

  it('has only list items directly inside every list', () => {
    renderWithRouter(<TimeOffSections />)
    for (const list of document.querySelectorAll('ul, ol')) {
      for (const child of list.children) expect(child.tagName).toBe('LI')
    }
  })
})
