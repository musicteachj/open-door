import { act, fireEvent, screen, within } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { CheckOut } from '@/api/generated'
import {
  CHECK_NOT_ENOUGH,
  CHECK_ONE_DAY,
  CHECK_OVERLAP,
  CHECK_SHORT_NOTICE,
  CHECK_SICK_HOURS,
  CHECK_WEEKEND,
  THIS_YEAR,
  TODAY,
} from '@/app/gallery/fixtures/timeoff'
import { MemoryRouter } from 'react-router'
import { renderWithRouter } from '@/test/render-with-router'
import { type DatePickerSelection } from './date-picker'
import { RequestForm, type HowMuch } from './request-form'

const CALENDAR = {
  today: TODAY,
  minDate: TODAY,
  scheduledWeekdays: [1, 2, 3, 4, 5],
  holidays: [{ day: '2026-11-26', name: 'Thanksgiving' }],
  pastLabel: 'Past days can’t be picked for PTO',
}

type Setup = {
  docked?: boolean
  type?: 'pto' | 'sick'
  start?: string
  end?: string
  howMuch?: HowMuch
  hours?: string
  check?: CheckOut | null
  approverName?: string | null
  submitting?: boolean
  checking?: boolean
  submitError?: string | null
  previewFailed?: boolean
  onRetryPreview?: () => void
  onClose?: () => void
  onSubmit?: (choice: { howMuch: HowMuch; hours: number | null }) => void
}

function Harness(setup: Setup) {
  const [type, setType] = useState<'pto' | 'sick'>(setup.type ?? 'pto')
  const [selection, setSelection] = useState<DatePickerSelection | undefined>(
    setup.start ? { start: setup.start, end: setup.end ?? setup.start } : undefined,
  )
  const [howMuch, setHowMuch] = useState<HowMuch>(setup.howMuch ?? 'full')
  const [hours, setHours] = useState(setup.hours ?? '3')
  return (
    <RequestForm
      docked={setup.docked ?? true}
      type={type}
      onTypeChange={setType}
      start={selection?.start}
      end={selection?.end}
      onDatesChange={setSelection}
      calendar={
        type === 'sick' ? { ...CALENDAR, minDate: '2026-09-20', pastLabel: 'Sick' } : CALENDAR
      }
      halfDayLabel="4 hours"
      howMuch={howMuch}
      onHowMuchChange={setHowMuch}
      hours={hours}
      onHoursChange={setHours}
      check={setup.check === undefined ? null : setup.check}
      approverName={setup.approverName === undefined ? 'Marcus Bell' : setup.approverName}
      thisYear={THIS_YEAR}
      submitting={setup.submitting}
      checking={setup.checking}
      submitError={setup.submitError}
      previewFailed={setup.previewFailed}
      onRetryPreview={setup.onRetryPreview}
      onSubmit={setup.onSubmit ?? (() => {})}
      onClose={setup.onClose ?? (() => {})}
    />
  )
}

function setup(options: Setup = {}) {
  return renderWithRouter(<Harness {...options} />)
}

const submitButton = () =>
  screen.getByRole('button', {
    name: /^(Request time off|Record sick time|Requesting…|Recording…)$/,
  })

describe('RequestForm, docked', () => {
  it('is a non-modal panel named by its title, 420 px wide', () => {
    setup()
    const panel = screen.getByRole('region', { name: 'Request time off' })
    expect(panel).toHaveClass('w-panel')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('moves focus to its title, an h2 with tabindex -1', () => {
    setup()
    const title = screen.getByRole('heading', { level: 2, name: 'Request time off' })
    expect(title).toHaveAttribute('tabindex', '-1')
    expect(title).toHaveFocus()
  })

  it('leaves focus alone when told not to take it, for a page that shows the form closed', () => {
    renderWithRouter(
      <RequestForm
        docked
        halfDayLabel="4 hours"
        autoFocusTitle={false}
        type="pto"
        onTypeChange={() => {}}
        onDatesChange={() => {}}
        calendar={CALENDAR}
        howMuch="full"
        onHowMuchChange={() => {}}
        hours="3"
        onHoursChange={() => {}}
        check={null}
        onSubmit={() => {}}
        onClose={() => {}}
      />,
    )
    expect(document.body).toHaveFocus()
  })

  it('has a fixed header and footer around a scrolling body', () => {
    setup()
    const panel = screen.getByRole('region', { name: 'Request time off' })
    expect(panel.querySelector('[data-slot="request-form-body"]')).toHaveClass('overflow-y-auto')
    expect(panel.querySelector('footer')).toBeInTheDocument()
  })

  it('closes with the Close button and with Cancel', async () => {
    const onClose = vi.fn<() => void>()
    const { user } = setup({ onClose })
    await user.click(screen.getByRole('button', { name: 'Close' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalledTimes(2)
  })
})

describe('RequestForm, the fields', () => {
  it('asks for the type with PTO selected', () => {
    setup()
    expect(screen.getByRole('radio', { name: 'PTO' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Sick time' })).not.toBeChecked()
  })

  it('shows How much only for a single day', () => {
    setup({ start: '2026-10-30' })
    expect(screen.getByRole('radiogroup', { name: 'How much' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Half day (4 hours)' })).toBeInTheDocument()
  })

  it('hides How much before a day is picked and for a range', () => {
    const { unmount } = setup()
    expect(screen.queryByRole('radiogroup', { name: 'How much' })).not.toBeInTheDocument()
    unmount()
    setup({ start: '2026-10-30', end: '2026-11-02' })
    expect(screen.queryByRole('radiogroup', { name: 'How much' })).not.toBeInTheDocument()
  })

  it('offers Some hours for sick time, and shows the stepper for it', async () => {
    const { user } = setup({ type: 'sick', start: '2026-10-22' })
    expect(screen.queryByRole('radio', { name: 'Half day (4 hours)' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Hours')).not.toBeInTheDocument()
    await user.click(screen.getByRole('radio', { name: 'Some hours' }))
    expect(screen.getByLabelText('Hours')).toHaveValue('3')
  })

  it('names the Dates field for the picked days', () => {
    setup({ start: '2026-10-30' })
    expect(screen.getByRole('button', { name: /Dates Friday, October 30/ })).toBeInTheDocument()
  })

  it('opens the picker under the field, and Done closes it and returns focus to the field', async () => {
    const { user } = setup()
    const field = screen.getByRole('button', { name: /^Dates/ })
    await user.click(field)
    expect(field).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('grid')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Done' }))
    expect(screen.queryByRole('grid')).not.toBeInTheDocument()
    expect(field).toHaveFocus()
  })

  it('closes only the picker on Escape inside it, not the panel', async () => {
    const onClose = vi.fn<() => void>()
    const { user } = setup({ onClose })
    const field = screen.getByRole('button', { name: /^Dates/ })
    await user.click(field)
    act(() => screen.getByRole('button', { name: /^Tuesday, October 20/ }).focus())
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('grid')).not.toBeInTheDocument()
    expect(field).toHaveFocus()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('closes the picker on Escape from the Dates field too', async () => {
    const { user } = setup()
    const field = screen.getByRole('button', { name: /^Dates/ })
    await user.click(field)
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('grid')).not.toBeInTheDocument()
    expect(field).toHaveFocus()
  })
})

describe('RequestForm, the preview and messages', () => {
  it('asks for dates before there is a check', () => {
    setup()
    expect(screen.getByText('Pick dates to see what this uses.')).toBeInTheDocument()
  })

  it('shows what this uses from the check', () => {
    setup({ start: '2026-10-30', check: CHECK_ONE_DAY })
    const preview = screen.getByRole('region', { name: 'What this uses' })
    expect(within(preview).getByText('8 hours (1 day)')).toBeInTheDocument()
  })

  it('warns about short notice without disabling the button', () => {
    setup({ start: '2026-11-02', end: '2026-11-05', check: CHECK_SHORT_NOTICE })
    expect(screen.getByRole('status')).toHaveTextContent(
      'More than 3 days usually needs 2 weeks’ notice. You can still request it.',
    )
    expect(submitButton()).not.toBeDisabled()
    expect(submitButton()).not.toHaveAttribute('aria-disabled', 'true')
  })

  it('refuses a request with not enough PTO and disables the button', () => {
    setup({ start: '2026-11-30', end: '2026-12-18', check: CHECK_NOT_ENOUGH })
    expect(screen.getByRole('alert')).toHaveTextContent(
      'You have 92 hours (11.5 days) available. This request needs 120 hours (15 days).',
    )
    expect(submitButton()).toBeDisabled()
  })

  it('refuses an overlap from the days that clash', () => {
    setup({ start: '2026-12-23', check: CHECK_OVERLAP })
    expect(screen.getByRole('alert')).toHaveTextContent(
      'You already have time off on Wednesday, December 23.',
    )
    expect(submitButton()).toBeDisabled()
  })

  it('shows the API text for a problem it has no sentence for', () => {
    setup({
      start: '2026-10-30',
      check: {
        ...CHECK_ONE_DAY,
        ok: false,
        problems: [{ code: 'too-long', text: 'That is too long.' }],
      },
    })
    expect(screen.getByRole('alert')).toHaveTextContent('That is too long.')
  })

  it('shows the refusal a failed send came back with, as an alert, and leaves the button usable', () => {
    setup({
      start: '2026-10-30',
      check: CHECK_ONE_DAY,
      submitError: 'Some of those days are already covered by another request.',
    })
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Some of those days are already covered by another request.',
    )
    expect(submitButton()).toBeEnabled()
  })

  it('says the preview did not load, as an alert, when told so, and never while checking', () => {
    setup({ start: '2026-10-30', check: null, previewFailed: true })
    expect(screen.getByRole('alert')).toHaveTextContent('The preview didn’t load.')
    expect(submitButton()).toBeDisabled()
  })

  it('offers Try again on the failed preview when a retry is wired, and calls it', async () => {
    const onRetryPreview = vi.fn<() => void>()
    const { user } = setup({
      start: '2026-10-30',
      check: null,
      previewFailed: true,
      onRetryPreview,
    })
    await user.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Try again' }))
    expect(onRetryPreview).toHaveBeenCalledTimes(1)
  })

  it('offers no Try again when nothing handles it', () => {
    setup({ start: '2026-10-30', check: null, previewFailed: true })
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })

  it('hides the preview message while a new check is on its way', () => {
    setup({ start: '2026-10-30', check: null, previewFailed: true, checking: true })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows no alert when the send has not failed', () => {
    setup({ start: '2026-10-30', check: CHECK_ONE_DAY, submitError: null })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('disables the button until the dates have a check that passes', () => {
    setup({ start: '2026-10-30' })
    expect(submitButton()).toBeDisabled()
  })

  it('disables the button for hours that are not a whole number from 1 to 8', () => {
    setup({
      type: 'sick',
      start: '2026-10-22',
      howMuch: 'hours',
      hours: '12',
      check: CHECK_SICK_HOURS,
    })
    expect(submitButton()).toBeDisabled()
  })
})

describe('RequestForm, the footer', () => {
  it('names the approver for PTO', () => {
    setup()
    expect(screen.getByText('Marcus Bell, your manager, reviews PTO requests.')).toBeInTheDocument()
  })

  it('says sick time needs no approval, and the button records it', () => {
    setup({ type: 'sick', start: '2026-10-22', check: CHECK_SICK_HOURS })
    expect(
      screen.getByText('Sick time is recorded right away, with no approval.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Record sick time' })).toBeEnabled()
  })

  it('puts the primary button first and Cancel second', () => {
    setup({ start: '2026-10-30', check: CHECK_WEEKEND })
    const buttons = within(document.querySelector('footer')!).getAllByRole('button')
    expect(buttons.map((button) => button.textContent)).toEqual(['Request time off', 'Cancel'])
  })

  it('submits when the button is pressed', async () => {
    const onSubmit = vi.fn<() => void>()
    const { user } = setup({ start: '2026-10-30', check: CHECK_ONE_DAY, onSubmit })
    await user.click(submitButton())
    expect(onSubmit).toHaveBeenCalledOnce()
  })

  it('shows Requesting… with aria-busy, locks the fields, and ignores another press', async () => {
    const onSubmit = vi.fn<() => void>()
    const { user } = setup({
      start: '2026-10-30',
      check: CHECK_ONE_DAY,
      submitting: true,
      onSubmit,
    })
    const button = screen.getByRole('button', { name: 'Requesting…' })
    expect(button).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('button', { name: /^Dates/ })).toBeDisabled()
    expect(screen.getByRole('radio', { name: 'PTO' })).toBeDisabled()
    expect(screen.getByRole('radio', { name: 'Full day' })).toBeDisabled()
    await user.click(button)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('shows Recording… for sick time', () => {
    setup({ type: 'sick', start: '2026-10-22', check: CHECK_SICK_HOURS, submitting: true })
    expect(screen.getByRole('button', { name: 'Recording…' })).toHaveAttribute('aria-busy', 'true')
  })
})

describe('RequestForm, while submitting', () => {
  it('locks Close and Cancel', async () => {
    const onClose = vi.fn<() => void>()
    const { user } = setup({ start: '2026-10-30', check: CHECK_ONE_DAY, submitting: true, onClose })
    expect(screen.getByRole('button', { name: 'Close' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).not.toHaveBeenCalled()
  })

  it('ignores Escape and a swipe down in the sheet', async () => {
    const onClose = vi.fn<() => void>()
    const { user } = setup({
      docked: false,
      start: '2026-10-30',
      check: CHECK_ONE_DAY,
      submitting: true,
      onClose,
    })
    await user.keyboard('{Escape}')
    expect(onClose).not.toHaveBeenCalled()
    const handle = document.querySelector('[data-slot="bottom-sheet-handle"]')!
    fireEvent.pointerDown(handle, { button: 0, clientY: 0, pointerId: 1 })
    fireEvent.pointerUp(handle, { clientY: 200, pointerId: 1 })
    expect(onClose).not.toHaveBeenCalled()
  })
})

describe('RequestForm, in a bottom sheet', () => {
  it('is a modal dialog named by its title, with focus on the title', () => {
    setup({ docked: false })
    const dialog = screen.getByRole('dialog', { name: 'Request time off' })
    expect(dialog).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Request time off' })).toHaveFocus()
  })

  it('closes on Escape when focus is not in the picker', async () => {
    const onClose = vi.fn<() => void>()
    const { user } = setup({ docked: false, onClose })
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('closes only the picker on Escape inside it, and leaves the sheet open', async () => {
    const onClose = vi.fn<() => void>()
    const { user } = setup({ docked: false, onClose })
    await user.click(screen.getByRole('button', { name: /^Dates/ }))
    act(() => screen.getByRole('button', { name: /^Tuesday, October 20/ }).focus())
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('grid')).not.toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByRole('dialog', { name: 'Request time off' })).toBeInTheDocument()
  })

  it('closes the picker on Escape from the Dates field, and leaves the sheet open', async () => {
    const onClose = vi.fn<() => void>()
    const { user } = setup({ docked: false, onClose })
    await user.click(screen.getByRole('button', { name: /^Dates/ }))
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('grid')).not.toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('closes with the Close button', async () => {
    const onClose = vi.fn<() => void>()
    const { user } = setup({ docked: false, onClose })
    await user.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  describe('RequestForm, how much follows the type', () => {
    it('goes back to Full day when Some hours is chosen and the type changes to PTO', async () => {
      const { user } = setup({
        type: 'sick',
        start: '2026-10-22',
        howMuch: 'hours',
        check: CHECK_SICK_HOURS,
      })
      await user.click(screen.getByRole('radio', { name: 'PTO' }))
      expect(screen.getByRole('radio', { name: 'Full day' })).toBeChecked()
      expect(screen.queryByLabelText('Hours')).not.toBeInTheDocument()
    })

    it('goes back to Full day when Half day is chosen and the type changes to sick time', async () => {
      const { user } = setup({
        type: 'pto',
        start: '2026-10-30',
        howMuch: 'half',
        check: CHECK_ONE_DAY,
      })
      await user.click(screen.getByRole('radio', { name: 'Sick time' }))
      expect(screen.getByRole('radio', { name: 'Full day' })).toBeChecked()
    })

    it('keeps a choice the new type also offers', async () => {
      const { user } = setup({
        type: 'pto',
        start: '2026-10-30',
        howMuch: 'full',
        check: CHECK_ONE_DAY,
      })
      await user.click(screen.getByRole('radio', { name: 'Sick time' }))
      expect(screen.getByRole('radio', { name: 'Full day' })).toBeChecked()
    })

    it('submits Full day for a how-much the type does not offer, whoever owns the state', async () => {
      const onSubmit = vi.fn<(choice: { howMuch: HowMuch; hours: number | null }) => void>()
      const { user } = renderWithRouter(
        <RequestForm
          docked
          halfDayLabel="4 hours"
          type="pto"
          onTypeChange={() => {}}
          start="2026-10-30"
          end="2026-10-30"
          onDatesChange={() => {}}
          calendar={CALENDAR}
          howMuch="hours"
          onHowMuchChange={() => {}}
          hours="3"
          onHoursChange={() => {}}
          check={CHECK_ONE_DAY}
          onSubmit={onSubmit}
          onClose={() => {}}
        />,
      )
      await user.click(submitButton())
      expect(onSubmit).toHaveBeenCalledWith({ howMuch: 'full', hours: null })
    })

    it('handles Escape in the picker once', async () => {
      const focus = vi.spyOn(HTMLElement.prototype, 'focus')
      const { user } = setup()
      const field = screen.getByRole('button', { name: /^Dates/ })
      await user.click(field)
      act(() => screen.getByRole('button', { name: /^Tuesday, October 20/ }).focus())
      focus.mockClear()
      await user.keyboard('{Escape}')
      expect(focus.mock.contexts.filter((context) => context === field)).toHaveLength(1)
      focus.mockRestore()
    })
  })

  describe('RequestForm, an open picker when sending starts', () => {
    it('closes the picker, so the dates cannot change mid-request', () => {
      const view = (submitting: boolean) => <Harness submitting={submitting} />
      const { rerender } = renderWithRouter(view(false))
      act(() => screen.getByRole('button', { name: /^Dates/ }).click())
      expect(screen.getByRole('grid')).toBeInTheDocument()
      rerender(<MemoryRouter>{view(true)}</MemoryRouter>)
      expect(screen.queryByRole('grid')).not.toBeInTheDocument()
    })
  })

  describe('RequestForm, the picker after a failed send', () => {
    it('stays closed when sending ends', () => {
      const view = (submitting: boolean) => <Harness submitting={submitting} />
      const { rerender } = renderWithRouter(view(false))
      act(() => screen.getByRole('button', { name: /^Dates/ }).click())
      expect(screen.getByRole('grid')).toBeInTheDocument()
      rerender(<MemoryRouter>{view(true)}</MemoryRouter>)
      rerender(<MemoryRouter>{view(false)}</MemoryRouter>)
      expect(screen.queryByRole('grid')).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: /^Dates/ })).toHaveAttribute(
        'aria-expanded',
        'false',
      )
    })
  })
})

describe('RequestForm, what it reports matches what it shows', () => {
  it('goes back to Full day when one day becomes a range', async () => {
    const { user } = setup({ start: '2026-10-30', howMuch: 'half', check: CHECK_ONE_DAY })
    await user.click(screen.getByRole('button', { name: /^Dates/ }))
    await user.click(screen.getByRole('button', { name: /^Thursday, October 29/ }))
    await user.click(screen.getByRole('button', { name: /^Friday, October 30/ }))
    expect(screen.queryByRole('radiogroup', { name: 'How much' })).not.toBeInTheDocument()
    // A new single day brings the control back, with Full day chosen.
    await user.click(screen.getByRole('button', { name: /^Wednesday, October 28/ }))
    expect(screen.getByRole('radio', { name: 'Full day' })).toBeChecked()
  })

  it('submits Full day for a range, whatever how-much it was handed', async () => {
    const onSubmit = vi.fn<(choice: { howMuch: HowMuch; hours: number | null }) => void>()
    const { user } = setup({
      start: '2026-11-02',
      end: '2026-11-05',
      howMuch: 'half',
      check: CHECK_SHORT_NOTICE,
      onSubmit,
    })
    await user.click(submitButton())
    expect(onSubmit).toHaveBeenCalledWith({ howMuch: 'full', hours: null })
  })

  it('submits the hours only for sick time on one day in hours', async () => {
    const onSubmit = vi.fn<(choice: { howMuch: HowMuch; hours: number | null }) => void>()
    const { user } = setup({
      type: 'sick',
      start: '2026-10-22',
      howMuch: 'hours',
      hours: '3',
      check: CHECK_SICK_HOURS,
      onSubmit,
    })
    await user.click(submitButton())
    expect(onSubmit).toHaveBeenCalledWith({ howMuch: 'hours', hours: 3 })
  })

  it('submits Full day with no hours for a full sick day, even with hours typed', async () => {
    const onSubmit = vi.fn<(choice: { howMuch: HowMuch; hours: number | null }) => void>()
    const { user } = setup({
      type: 'sick',
      start: '2026-10-22',
      howMuch: 'full',
      hours: '3',
      check: CHECK_SICK_HOURS,
      onSubmit,
    })
    await user.click(submitButton())
    expect(onSubmit).toHaveBeenCalledWith({ howMuch: 'full', hours: null })
  })

  describe('RequestForm, while a check is on its way', () => {
    it('disables Submit and marks the preview as updating, however good the old check was', () => {
      setup({ start: '2026-10-30', check: CHECK_ONE_DAY, checking: true })
      expect(submitButton()).toBeDisabled()
      expect(document.querySelector('[data-slot="preview-live"]')).toHaveAttribute(
        'aria-busy',
        'true',
      )
      expect(screen.getByRole('region', { name: 'What this uses' })).toHaveClass('text-ink-muted')
    })

    it('is ready when the check arrives', () => {
      setup({ start: '2026-10-30', check: CHECK_ONE_DAY, checking: false })
      expect(submitButton()).toBeEnabled()
      expect(document.querySelector('[data-slot="preview-live"]')).not.toHaveAttribute(
        'aria-busy',
        'true',
      )
    })
  })

  describe('RequestForm, stale messages while checking', () => {
    it('hides the short-notice warning and the refusals that belong to the old check', () => {
      const { unmount } = setup({
        start: '2026-11-02',
        end: '2026-11-05',
        check: CHECK_SHORT_NOTICE,
      })
      expect(screen.getByText(/usually needs 2 weeks/)).toBeInTheDocument()
      unmount()
      const again = setup({
        start: '2026-11-02',
        end: '2026-11-05',
        check: CHECK_SHORT_NOTICE,
        checking: true,
      })
      expect(screen.queryByText(/usually needs 2 weeks/)).not.toBeInTheDocument()
      again.unmount()
      setup({ start: '2026-11-30', end: '2026-12-18', check: CHECK_NOT_ENOUGH, checking: true })
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    })
  })
})
