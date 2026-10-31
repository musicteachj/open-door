import { within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithRouter } from '@/test/render-with-router'
import { CasesSections } from './cases-sections'

// The browser tests address each state by its heading's id, so the ids are part of the contract.
const IDS = [
  'case-sensitive-offer',
  'case-form-open',
  'case-form-category',
  'case-form-short-reply',
  'case-form-errors',
  'case-form-limit',
  'case-form-sending',
  'case-form-send-failed',
  'case-sent-panel',
  'case-limit-panel',
  'case-crisis-offer',
  'case-unavailable-write-to-hr',
  'case-page-form',
  'case-page-form-empty',
  'case-page-sent',
  'case-page-sent-crisis',
  'case-page-limit',
]

const section = (id: string) => within(document.getElementById(id)!.closest('section')!)

describe('CasesSections', () => {
  it('has a heading with a stable id for every state, in page order', () => {
    const { container } = renderWithRouter(<CasesSections />)
    const found = [...container.querySelectorAll('h3[id]')]
      .map((heading) => heading.id)
      .filter((id) => /^[a-z][a-z0-9-]*$/.test(id))
    expect(found).toEqual(IDS)
  })

  it('does not take focus', () => {
    renderWithRouter(<CasesSections />)
    expect(document.body).toHaveFocus()
  })

  it('opens the live panel, closes it with Not now back onto the button, and sends', async () => {
    const { user } = renderWithRouter(<CasesSections />)
    const live = section('case-sensitive-offer')
    await user.click(live.getByRole('button', { name: 'Open a confidential case' }))
    expect(live.getByRole('heading', { name: 'Open a confidential case' })).toHaveFocus()
    await user.click(live.getByRole('button', { name: 'Not now' }))
    expect(live.getByRole('button', { name: 'Open a confidential case' })).toHaveFocus()
    await user.click(live.getByRole('button', { name: 'Open a confidential case' }))
    await user.click(live.getByRole('radio', { name: 'Pay concern' }))
    await user.click(live.getByRole('button', { name: 'Send to HR' }))
    expect(live.getByRole('status')).toHaveTextContent(
      'Sent to HR. HR replies by Wednesday, October 28. You can see its status in My cases.',
    )
  })

  it('shows the errors, the limit, sending, and the failure in their frames', () => {
    renderWithRouter(<CasesSections />)
    const errors = section('case-form-errors')
    expect(errors.getByText('Choose what this is about.')).toBeInTheDocument()
    expect(errors.getByText(/looks like a Social Security/)).toBeInTheDocument()
    expect(
      section('case-form-limit').getByText('4,000 of 4,000 characters. Shorten it to send.'),
    ).toBeInTheDocument()
    expect(
      section('case-form-sending').getByRole('button', { name: 'Sending…' }),
    ).toBeInTheDocument()
    expect(
      section('case-form-send-failed').getByRole('button', { name: 'Try again' }),
    ).toBeInTheDocument()
    expect(section('case-form-short-reply').getByText(/^Add what happened/)).toBeInTheDocument()
    expect(section('case-page-form-empty').getByText('0 of 4,000 characters')).toBeInTheDocument()
  })

  it('shows the crisis panel with a secondary button, and Write to HR on the unavailable panel', () => {
    renderWithRouter(<CasesSections />)
    expect(
      section('case-crisis-offer').getByRole('button', { name: 'Open a confidential case' }),
    ).not.toHaveClass('bg-primary')
    expect(
      section('case-unavailable-write-to-hr').getByRole('link', { name: 'Write to HR' }),
    ).toBeInTheDocument()
    expect(
      section('case-page-sent-crisis').getByRole('heading', { name: 'Reach a person right now' }),
    ).toBeInTheDocument()
    // On My cases the limit line has no link to the page it is on; the panel's does.
    expect(
      section('case-page-limit').queryByRole('link', { name: 'View your cases' }),
    ).not.toBeInTheDocument()
    expect(
      section('case-limit-panel').getByRole('link', { name: 'View your cases' }),
    ).toBeInTheDocument()
  })
})
