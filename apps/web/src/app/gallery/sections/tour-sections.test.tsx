import { render, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ToastProvider, ToastViewport } from '@/components/ui/toast'
import { TourSections } from './tour-sections'

// The browser tests address each state by its heading's id, so the ids are part of the contract.
const IDS = [
  'tour-coach-step-1',
  'tour-coach-step-6',
  'tour-coach-result',
  'tour-coach-missing',
  'tour-coach-no-chips',
  'tour-chip-states',
  'tour-ring',
  'tour-end-card',
  'tour-menu-idle',
  'tour-menu-progress',
  'tour-start-dialog',
  'tour-toast-leave',
  'tour-toast-switch',
  'tour-start-button',
  'tour-start-button-starting',
  'tour-live',
]

const section = (id: string) => within(document.getElementById(id)!.closest('section')!)

function renderSections() {
  return render(
    <ToastProvider>
      <TourSections />
      <ToastViewport />
    </ToastProvider>,
  )
}

describe('TourSections', () => {
  it('has a heading with a stable id for every state, in page order', () => {
    const { container } = renderSections()
    const found = [...container.querySelectorAll('h3[id]')]
      .map((heading) => heading.id)
      .filter((id) => /^[a-z][a-z0-9-]*$/.test(id))
    expect(found).toEqual(IDS)
  })

  it('does not take focus', () => {
    renderSections()
    expect(document.body).toHaveFocus()
  })

  it('draws step 1 without Back, and the missing line as a status', () => {
    renderSections()
    expect(section('tour-coach-step-1').queryByRole('button', { name: 'Back' })).toBeNull()
    expect(section('tour-coach-missing').getByRole('status')).toHaveTextContent(
      /^The assistant usually shows a confirm card here/,
    )
  })

  it('draws step 6 with one of its two chips sent', () => {
    renderSections()
    const step = section('tour-coach-step-6')
    expect(
      step.getByRole('button', { name: 'What’s Leo’s home address?, sent' }),
    ).toBeInTheDocument()
    expect(step.getByRole('button', { name: 'Skip this step' })).toBeInTheDocument()
  })

  it('shows the live demo: send, a fake card, Next, then Leave returns focus', async () => {
    const user = userEvent.setup()
    renderSections()
    const live = section('tour-live')
    await user.click(live.getByRole('button', { name: 'Start the demo' }))
    const dialog = within(live.getByRole('dialog'))
    expect(dialog.getByRole('heading', { level: 2 })).toHaveFocus()
    await user.click(dialog.getByRole('button', { name: 'Book next Friday off.' }))
    expect(dialog.getByRole('button', { name: 'Book next Friday off., sent' })).toBeInTheDocument()
    expect(await dialog.findByRole('button', { name: 'Next' })).toBeInTheDocument()
    expect(live.getByRole('button', { name: 'Confirm' })).toBeInTheDocument()
    await user.click(dialog.getByRole('button', { name: 'Leave the tour' }))
    expect(live.queryByRole('dialog')).toBeNull()
    expect(live.getByRole('button', { name: 'Start the demo' })).toHaveFocus()
  })

  it('shows the missing line instead of the card when asked', async () => {
    const user = userEvent.setup()
    renderSections()
    const live = section('tour-live')
    await user.click(live.getByRole('button', { name: 'Show the missing line' }))
    await user.click(live.getByRole('button', { name: 'Start the demo' }))
    const dialog = within(live.getByRole('dialog'))
    await user.click(dialog.getByRole('button', { name: 'Book next Friday off.' }))
    expect(await dialog.findByRole('status')).toHaveTextContent(/^The assistant usually shows/)
    expect(live.queryByRole('button', { name: 'Confirm' })).toBeNull()
  })
})
