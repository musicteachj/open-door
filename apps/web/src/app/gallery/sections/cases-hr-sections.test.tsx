import { act, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { resetAnnouncer } from '@/lib/announce'
import { renderWithRouter } from '@/test/render-with-router'
import { CasesHrSections } from './cases-hr-sections'

// The browser tests address each state by its heading's id, so the ids are part of the contract.
const IDS = [
  'case-list-empty',
  'case-list-rows',
  'case-badges',
  'case-queue-open',
  'case-queue-closed',
  'case-queue-empty',
  'case-queue-facts',
  'case-detail-new',
  'case-detail-revealed',
  'case-detail-in-review',
  'case-summary-pending',
  'case-summary-failed',
  'case-summary-crisis',
  'case-words-loading',
  'case-words-failed',
  'case-detail-closed',
  'case-dialog-review',
  'case-dialog-close',
  'case-detail-own',
]

const section = (id: string) => within(document.getElementById(id)!.closest('section')!)
const timelineRows = (id: string) =>
  section(id).getByRole('region', { name: 'Timeline' }).querySelectorAll('li').length

describe('CasesHrSections', () => {
  it('has a heading with a stable id for every state, in page order', () => {
    const { container } = renderWithRouter(<CasesHrSections />)
    const found = [...container.querySelectorAll('h3[id]')]
      .map((heading) => heading.id)
      .filter((id) => /^[a-z][a-z0-9-]*$/.test(id))
    expect(found).toEqual(IDS)
  })

  it('does not take focus', () => {
    renderWithRouter(<CasesHrSections />)
    expect(document.body).toHaveFocus()
  })

  it('shows the queue as the frames do, with "Reply due today" and a link per case', () => {
    renderWithRouter(<CasesHrSections />)
    const open = section('case-queue-open')
    expect(open.getAllByRole('link')).toHaveLength(4)
    expect(open.getByText('Reply due today')).toBeInTheDocument()
    expect(open.getByRole('radio', { name: 'Open' })).toBeChecked()
    expect(section('case-queue-closed').getAllByRole('link')).toHaveLength(1)
    expect(section('case-queue-empty').getByRole('status')).toHaveTextContent(
      'No new cases. A case appears here as soon as someone sends one.',
    )
  })

  it('shows the facts: overdue, due today, the crisis fact, and HR’s own case without one', () => {
    renderWithRouter(<CasesHrSections />)
    const facts = section('case-queue-facts')
    expect(facts.getByText('Reply was due Mon, Oct 26')).toBeInTheDocument()
    // Keisha's, and HR's own case, whose reply is due the same day.
    expect(facts.getAllByText('Reply due today')).toHaveLength(2)
    expect(facts.getAllByText('The safety check routed this message to crisis text.')).toHaveLength(
      1,
    )
    expect(facts.getAllByRole('link')).toHaveLength(6)
  })

  it('the revealed state adds one timeline row on each Show and none on Hide', async () => {
    const { user } = renderWithRouter(<CasesHrSections />)
    const live = section('case-detail-revealed')
    expect(timelineRows('case-detail-revealed')).toBe(4)
    expect(live.getByText('Dana Whitfield read Priya’s words')).toBeInTheDocument()
    await user.click(live.getByRole('button', { name: 'Hide Priya’s words' }))
    expect(timelineRows('case-detail-revealed')).toBe(4)
    expect(live.getByRole('button', { name: 'Show Priya’s words' })).toHaveFocus()
    await user.click(live.getByRole('button', { name: 'Show Priya’s words' }))
    expect(timelineRows('case-detail-revealed')).toBe(5)
    resetAnnouncer()
  })

  it('a new case starts locked, and opening the words unlocks it', async () => {
    const { user } = renderWithRouter(<CasesHrSections />)
    const frame = section('case-detail-new')
    expect(frame.getByRole('button', { name: 'Start review' })).toHaveAttribute(
      'aria-disabled',
      'true',
    )
    await user.click(frame.getByRole('button', { name: 'Show Priya’s words' }))
    expect(frame.getByRole('button', { name: 'Start review' })).not.toHaveAttribute('aria-disabled')
    resetAnnouncer()
  })

  it('confirming Start review moves focus to Close case; confirming Close moves it to the heading', async () => {
    const { user } = renderWithRouter(<CasesHrSections />)
    const frame = section('case-detail-revealed')
    await user.click(frame.getByRole('button', { name: 'Start review' }))
    const dialog = within(document.body).getByRole('alertdialog')
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toHaveFocus()
    await user.click(within(dialog).getByRole('button', { name: 'Start review' }))
    await act(async () => {})
    expect(frame.getByRole('button', { name: 'Close case' })).toHaveFocus()
    expect(frame.getByText('In review')).toBeInTheDocument()
    await user.click(frame.getByRole('button', { name: 'Close case' }))
    await user.click(
      within(within(document.body).getByRole('alertdialog')).getByRole('button', {
        name: 'Close case',
      }),
    )
    await act(async () => {})
    expect(frame.getByRole('heading', { level: 1 })).toHaveFocus()
    expect(frame.getByText('This case is closed.')).toBeInTheDocument()
    expect(frame.queryByText('My manager keeps making comments about my age.')).toBeNull()
    resetAnnouncer()
  })

  it('Cancel returns focus to the button that opened the dialog', async () => {
    const { user } = renderWithRouter(<CasesHrSections />)
    const frame = section('case-detail-in-review')
    const close = frame.getByRole('button', { name: 'Close case' })
    await user.click(close)
    await user.click(
      within(within(document.body).getByRole('alertdialog')).getByRole('button', {
        name: 'Cancel',
      }),
    )
    await act(async () => {})
    expect(close).toHaveFocus()
  })

  it('the own case shows the header and the notice only', () => {
    renderWithRouter(<CasesHrSections />)
    const own = section('case-detail-own')
    expect(
      own.getByText('You opened this case, so you can’t act on it or read it here.'),
    ).toBeInTheDocument()
    expect(own.queryByRole('button')).toBeNull()
    expect(own.queryByRole('region', { name: 'Timeline' })).toBeNull()
    expect(own.queryByRole('region', { name: 'AI summary' })).toBeNull()
  })

  it('shows the summary and words states in their frames', () => {
    renderWithRouter(<CasesHrSections />)
    expect(section('case-summary-pending').getByText('Writing the summary…')).toBeInTheDocument()
    expect(
      section('case-summary-failed').getByRole('button', { name: 'Try again' }),
    ).toBeInTheDocument()
    const crisis = section('case-summary-crisis')
    expect(
      crisis.getByText('No AI summary for this case. The safety check routed it to crisis text.'),
    ).toBeInTheDocument()
    expect(
      crisis.getAllByText('The safety check routed this message to crisis text.'),
    ).toHaveLength(1)
    expect(crisis.getByText('The safety check routed it to crisis text')).toBeInTheDocument()
    expect(
      section('case-words-loading').getByRole('button', { name: 'Show Priya’s words' }),
    ).toHaveAttribute('aria-busy', 'true')
    expect(
      section('case-words-failed').getByText('Priya’s words couldn’t be opened. Please try again.'),
    ).toBeInTheDocument()
  })
})
