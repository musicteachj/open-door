import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DatePicker, type DatePickerSelection } from './date-picker'

const TODAY = '2026-10-20'
const HOLIDAYS = [
  { day: '2026-11-26', name: 'Thanksgiving' },
  { day: '2026-12-25', name: 'Christmas Day' },
]

type Setup = {
  minDate?: string
  maxDate?: string
  start?: string
  end?: string
  pastLabel?: string
  onDone?: () => void
  onChange?: (selection: DatePickerSelection) => void
}

function Picker({ start, end, onChange, ...rest }: Setup) {
  const [selection, setSelection] = useState<DatePickerSelection | undefined>(
    start ? { start, end: end ?? start } : undefined,
  )
  return (
    <>
      <button>Before</button>
      <DatePicker
        id="picker"
        today={TODAY}
        minDate={rest.minDate ?? TODAY}
        maxDate={rest.maxDate}
        scheduledWeekdays={[1, 2, 3, 4, 5]}
        holidays={HOLIDAYS}
        start={selection?.start}
        end={selection?.end}
        pastLabel={rest.pastLabel ?? 'Past days can’t be picked for PTO'}
        onChange={(next) => {
          setSelection(next)
          onChange?.(next)
        }}
        onDone={rest.onDone ?? (() => {})}
      />
    </>
  )
}

/** A day's button, found by the start of its accessible name: "Friday, October 23". */
function day(name: string) {
  return screen.getByRole('button', { name: new RegExp(`^${name}(,|$)`) })
}

const grid = () => screen.getByRole('grid')

describe('DatePicker structure', () => {
  it('is a grid named by the month, with a row of weekday headers and one cell per day', () => {
    render(<Picker />)
    expect(screen.getByRole('grid', { name: 'October 2026' })).toBeInTheDocument()
    const headers = within(grid()).getAllByRole('columnheader')
    expect(headers.map((header) => header.textContent)).toEqual([
      'Su',
      'Mo',
      'Tu',
      'We',
      'Th',
      'Fr',
      'Sa',
    ])
    expect(headers.map((header) => header.getAttribute('aria-label'))).toEqual([
      'Sunday',
      'Monday',
      'Tuesday',
      'Wednesday',
      'Thursday',
      'Friday',
      'Saturday',
    ])
    expect(within(grid()).getAllByRole('button')).toHaveLength(31)
    // The header row and five weeks.
    expect(within(grid()).getAllByRole('row')).toHaveLength(6)
  })

  it('announces the month politely when it changes', () => {
    render(<Picker />)
    expect(screen.getByText('October 2026')).toHaveAttribute('aria-live', 'polite')
  })

  it('has a status line, a legend, and a Done button', () => {
    render(<Picker />)
    expect(screen.getByRole('status')).toHaveTextContent('Pick a day, or a first and last day.')
    expect(screen.getByText('Not on your schedule')).toBeInTheDocument()
    expect(screen.getByText('Company holiday')).toBeInTheDocument()
    expect(screen.getByText('Today')).toBeInTheDocument()
    expect(screen.getByText('Past days can’t be picked for PTO')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Done' })).toBeInTheDocument()
  })

  it('carries the id its field points at', () => {
    const { container } = render(<Picker />)
    expect(container.querySelector('#picker')).not.toBeNull()
  })

  it('opens on the month of the selection', () => {
    render(<Picker minDate="2026-10-20" start="2026-11-25" end="2026-11-27" />)
    expect(screen.getByRole('grid', { name: 'November 2026' })).toBeInTheDocument()
  })
})

describe('DatePicker day names', () => {
  it('names a plain day by its date', () => {
    render(<Picker />)
    expect(screen.getByRole('button', { name: 'Wednesday, October 21' })).toBeInTheDocument()
  })

  it('names today', () => {
    render(<Picker />)
    expect(screen.getByRole('button', { name: 'Tuesday, October 20, today' })).toBeInTheDocument()
  })

  it('names a day off the schedule', () => {
    render(<Picker />)
    expect(
      screen.getByRole('button', { name: 'Saturday, October 31, not on your schedule' }),
    ).toBeInTheDocument()
  })

  it('names a day that can’t be picked', () => {
    render(<Picker />)
    const button = screen.getByRole('button', { name: 'Monday, October 19, not available' })
    expect(button).toHaveAttribute('aria-disabled', 'true')
  })

  it('names a holiday', async () => {
    const user = userEvent.setup()
    render(<Picker />)
    await user.click(screen.getByRole('button', { name: 'Next month' }))
    expect(
      screen.getByRole('button', { name: 'Thursday, November 26, Thanksgiving, company holiday' }),
    ).toBeInTheDocument()
  })
})

describe('DatePicker keyboard', () => {
  it('has one tab stop, on today, and Tab leaves the grid', async () => {
    const user = userEvent.setup()
    render(<Picker />)
    const stops = within(grid())
      .getAllByRole('button')
      .filter((button) => button.tabIndex === 0)
    expect(stops).toHaveLength(1)
    expect(stops[0]).toHaveAccessibleName('Tuesday, October 20, today')
    await user.click(screen.getByRole('button', { name: 'Before' }))
    await user.tab() // Previous month
    await user.tab() // Next month
    await user.tab()
    expect(day('Tuesday, October 20')).toHaveFocus()
    await user.tab()
    expect(screen.getByRole('button', { name: 'Done' })).toHaveFocus()
  })

  it('moves the one tab stop with focus', async () => {
    const user = userEvent.setup()
    render(<Picker />)
    day('Tuesday, October 20').focus()
    await user.keyboard('{ArrowRight}')
    expect(day('Wednesday, October 21')).toHaveFocus()
    expect(day('Wednesday, October 21')).toHaveAttribute('tabindex', '0')
    expect(day('Tuesday, October 20')).toHaveAttribute('tabindex', '-1')
  })

  it('moves by a day with Left and Right and by a week with Up and Down', async () => {
    const user = userEvent.setup()
    render(<Picker />)
    day('Tuesday, October 20').focus()
    await user.keyboard('{ArrowDown}')
    expect(day('Tuesday, October 27')).toHaveFocus()
    await user.keyboard('{ArrowUp}{ArrowLeft}')
    expect(day('Monday, October 19')).toHaveFocus()
  })

  it('passes over a day that can’t be picked, which stays focusable', async () => {
    const user = userEvent.setup()
    render(<Picker />)
    day('Tuesday, October 20').focus()
    await user.keyboard('{ArrowLeft}')
    expect(screen.getByRole('button', { name: /^Monday, October 19/ })).toHaveFocus()
  })

  it('goes to the next month and its first days with the arrows', async () => {
    const user = userEvent.setup()
    render(<Picker />)
    day('Saturday, October 31').focus()
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('grid', { name: 'November 2026' })).toBeInTheDocument()
    expect(day('Sunday, November 1')).toHaveFocus()
  })

  it('moves a month with Page Down and Page Up, keeping the date', async () => {
    const user = userEvent.setup()
    render(<Picker minDate="2026-09-20" />)
    day('Tuesday, October 20').focus()
    await user.keyboard('{PageDown}')
    expect(day('Friday, November 20')).toHaveFocus()
    await user.keyboard('{PageUp}{PageUp}')
    expect(screen.getByRole('grid', { name: 'September 2026' })).toBeInTheDocument()
    expect(day('Sunday, September 20')).toHaveFocus()
  })

  it('clamps the date to a shorter month', async () => {
    const user = userEvent.setup()
    render(<Picker minDate="2026-09-20" />)
    day('Saturday, October 31').focus()
    await user.keyboard('{PageDown}')
    expect(day('Monday, November 30')).toHaveFocus()
    await user.keyboard('{PageUp}{PageUp}')
    expect(day('Wednesday, September 30')).toHaveFocus()
  })

  it('goes to the ends of the week with Home and End', async () => {
    const user = userEvent.setup()
    render(<Picker />)
    day('Wednesday, October 21').focus()
    await user.keyboard('{Home}')
    expect(day('Sunday, October 18')).toHaveFocus()
    await user.keyboard('{End}')
    expect(day('Saturday, October 24')).toHaveFocus()
  })

  it('does not move focus before the first month or after the last one it allows', async () => {
    const user = userEvent.setup()
    render(<Picker minDate="2026-10-20" maxDate="2026-11-15" />)
    day('Thursday, October 1').focus()
    await user.keyboard('{ArrowLeft}')
    expect(day('Thursday, October 1')).toHaveFocus()
    await user.keyboard('{PageUp}')
    expect(day('Thursday, October 1')).toHaveFocus()
    expect(screen.getByRole('grid', { name: 'October 2026' })).toBeInTheDocument()
    await user.keyboard('{PageDown}')
    expect(screen.getByRole('grid', { name: 'November 2026' })).toBeInTheDocument()
    day('Monday, November 30').focus()
    await user.keyboard('{ArrowRight}')
    expect(day('Monday, November 30')).toHaveFocus()
  })

  it('selects a day with Enter', async () => {
    const onChange = vi.fn<(selection: DatePickerSelection) => void>()
    const user = userEvent.setup()
    render(<Picker onChange={onChange} />)
    day('Friday, October 23').focus()
    await user.keyboard('{Enter}')
    expect(onChange).toHaveBeenCalledWith({ start: '2026-10-23', end: '2026-10-23' })
  })

  it('selects a day with Space', async () => {
    const onChange = vi.fn<(selection: DatePickerSelection) => void>()
    const user = userEvent.setup()
    render(<Picker onChange={onChange} />)
    day('Friday, October 23').focus()
    await user.keyboard(' ')
    expect(onChange).toHaveBeenCalledWith({ start: '2026-10-23', end: '2026-10-23' })
  })

  it('closes on Escape, from a day or from a button', async () => {
    const onDone = vi.fn<() => void>()
    const user = userEvent.setup()
    render(<Picker onDone={onDone} />)
    day('Tuesday, October 20').focus()
    await user.keyboard('{Escape}')
    expect(onDone).toHaveBeenCalledTimes(1)
    screen.getByRole('button', { name: 'Next month' }).focus()
    await user.keyboard('{Escape}')
    expect(onDone).toHaveBeenCalledTimes(2)
  })

  it('closes with Done', async () => {
    const onDone = vi.fn<() => void>()
    render(<Picker onDone={onDone} />)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Done' }))
    expect(onDone).toHaveBeenCalledTimes(1)
  })
})

describe('DatePicker choosing days', () => {
  it('makes the first click a range of one day, and says to pick the last', async () => {
    const onChange = vi.fn<(selection: DatePickerSelection) => void>()
    const user = userEvent.setup()
    render(<Picker onChange={onChange} />)
    await user.click(day('Friday, October 23'))
    expect(onChange).toHaveBeenLastCalledWith({ start: '2026-10-23', end: '2026-10-23' })
    expect(screen.getByRole('status')).toHaveTextContent(
      'Now pick the last day. For one day, choose Done.',
    )
  })

  it('ends the range with a later day', async () => {
    const onChange = vi.fn<(selection: DatePickerSelection) => void>()
    const user = userEvent.setup()
    render(<Picker onChange={onChange} />)
    await user.click(day('Friday, October 23'))
    await user.click(day('Tuesday, October 27'))
    expect(onChange).toHaveBeenLastCalledWith({ start: '2026-10-23', end: '2026-10-27' })
    expect(screen.getByRole('status')).toHaveTextContent('Selected: Fri, Oct 23 to Tue, Oct 27')
  })

  it('restarts the range when the second day is before the first', async () => {
    const onChange = vi.fn<(selection: DatePickerSelection) => void>()
    const user = userEvent.setup()
    render(<Picker onChange={onChange} />)
    await user.click(day('Friday, October 23'))
    await user.click(day('Wednesday, October 21'))
    expect(onChange).toHaveBeenLastCalledWith({ start: '2026-10-21', end: '2026-10-21' })
    expect(screen.getByRole('status')).toHaveTextContent('Now pick the last day.')
  })

  it('keeps one day when the same day is chosen again', async () => {
    const onChange = vi.fn<(selection: DatePickerSelection) => void>()
    const user = userEvent.setup()
    render(<Picker onChange={onChange} />)
    await user.click(day('Friday, October 23'))
    await user.click(day('Friday, October 23'))
    expect(onChange).toHaveBeenLastCalledWith({ start: '2026-10-23', end: '2026-10-23' })
    expect(screen.getByRole('status')).toHaveTextContent('Selected: Fri, Oct 23')
  })

  it('starts a new range from a click after a finished one', async () => {
    const onChange = vi.fn<(selection: DatePickerSelection) => void>()
    const user = userEvent.setup()
    render(<Picker onChange={onChange} start="2026-10-23" end="2026-10-27" />)
    await user.click(day('Wednesday, October 28'))
    expect(onChange).toHaveBeenLastCalledWith({ start: '2026-10-28', end: '2026-10-28' })
  })

  it('does not select a day that can’t be picked, though it takes focus', async () => {
    const onChange = vi.fn<(selection: DatePickerSelection) => void>()
    const user = userEvent.setup()
    render(<Picker onChange={onChange} />)
    const past = screen.getByRole('button', { name: 'Monday, October 19, not available' })
    await user.click(past)
    expect(onChange).not.toHaveBeenCalled()
    expect(past).toHaveFocus()
  })

  it('does not select a day after the last allowed one', async () => {
    const onChange = vi.fn<(selection: DatePickerSelection) => void>()
    const user = userEvent.setup()
    render(<Picker onChange={onChange} maxDate="2026-10-28" />)
    await user.click(screen.getByRole('button', { name: 'Thursday, October 29, not available' }))
    expect(onChange).not.toHaveBeenCalled()
  })

  it('selects a day off the schedule, since it is only skipped', async () => {
    const onChange = vi.fn<(selection: DatePickerSelection) => void>()
    const user = userEvent.setup()
    render(<Picker onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /^Saturday, October 24/ }))
    expect(onChange).toHaveBeenCalledWith({ start: '2026-10-24', end: '2026-10-24' })
  })
})

describe('DatePicker keys with a modifier', () => {
  it.each(['Alt', 'Control', 'Meta'])(
    'leaves %s plus an arrow to the browser',
    async (modifier) => {
      const user = userEvent.setup()
      render(<Picker />)
      day('Tuesday, October 20').focus()
      await user.keyboard(`{${modifier}>}{ArrowRight}{/${modifier}}`)
      expect(day('Tuesday, October 20')).toHaveFocus()
    },
  )
})

describe('DatePicker in a time zone behind UTC', () => {
  const original = process.env.TZ
  afterEach(() => {
    if (original === undefined) delete process.env.TZ
    else process.env.TZ = original
  })

  it('names the days and the month the same as anywhere', () => {
    process.env.TZ = 'America/Los_Angeles'
    expect(
      new Date('2026-10-23').toLocaleDateString('en-US', { month: 'long', day: 'numeric' }),
    ).toBe('October 22')
    render(<Picker />)
    expect(screen.getByRole('grid', { name: 'October 2026' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Friday, October 23' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Tuesday, October 20, today' })).toBeInTheDocument()
  })
})

describe('DatePicker grid semantics', () => {
  it('says a range can be chosen, since the days between are selected too', () => {
    render(<Picker />)
    expect(grid()).toHaveAttribute('aria-multiselectable', 'true')
  })
})

describe('DatePicker preview', () => {
  it('drops the old preview when a new range starts from the keyboard', async () => {
    const user = userEvent.setup()
    render(<Picker />)
    day('Tuesday, October 27').focus()
    await user.keyboard('{Enter}')
    await user.keyboard('{ArrowRight}{ArrowRight}{ArrowRight}{Enter}')
    // Range finished: October 27 to 30. Walk back and start a new one.
    await user.keyboard(
      '{ArrowLeft}{ArrowLeft}{ArrowLeft}{ArrowLeft}{ArrowLeft}{ArrowLeft}{ArrowLeft}',
    )
    expect(day('Friday, October 23')).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(screen.getByRole('status')).toHaveTextContent('Now pick the last day.')
    const banded = [...grid().querySelectorAll('td[data-band]')]
    expect(banded).toEqual([])
  })
})

describe('DatePicker marks', () => {
  it('fills a day off the schedule', () => {
    render(<Picker />)
    const button = screen.getByRole('button', { name: /^Saturday, October 24/ })
    expect(button).toHaveClass('bg-surface-hover', 'text-ink-muted')
  })

  it('strikes a day that can’t be picked through, with no fill, even on a weekend', () => {
    render(<Picker />)
    const weekday = screen.getByRole('button', { name: /^Monday, October 19/ })
    const weekend = screen.getByRole('button', { name: /^Sunday, October 18/ })
    for (const button of [weekday, weekend]) {
      expect(button).toHaveClass('line-through', 'text-disabled-fg')
      expect(button).not.toHaveClass('bg-surface-hover')
    }
  })

  it('rings today and sets it semibold', () => {
    render(<Picker />)
    expect(screen.getByRole('button', { name: /^Tuesday, October 20/ })).toHaveClass(
      'font-semibold',
      'shadow-[inset_0_0_0_1px_var(--color-input-border)]',
    )
  })

  it('lights a day on hover with a fill, not a ring', () => {
    render(<Picker />)
    const button = screen.getByRole('button', { name: /^Wednesday, October 21/ })
    expect(button).toHaveClass('hover:bg-neutral-hover')
    expect(button.className).not.toContain('hover:shadow')
  })

  it('does not light a day that can’t be picked on hover', () => {
    render(<Picker />)
    expect(screen.getByRole('button', { name: /^Monday, October 19/ }).className).not.toContain(
      'hover:',
    )
  })

  it('fills the chosen days with primary and white text', () => {
    render(<Picker start="2026-10-23" end="2026-10-27" />)
    for (const name of ['Friday, October 23', 'Tuesday, October 27']) {
      expect(day(name)).toHaveClass('bg-primary', 'text-on-primary')
    }
    expect(day('Monday, October 26')).not.toHaveClass('bg-primary')
  })

  it('puts a primary tint band behind the range, skipped days included', () => {
    render(<Picker start="2026-10-23" end="2026-10-27" />)
    const cell = (name: string) => day(name).closest('td')!
    expect(cell('Friday, October 23')).toHaveAttribute('data-band', 'start')
    expect(cell('Tuesday, October 27')).toHaveAttribute('data-band', 'end')
    for (const name of ['Saturday, October 24', 'Sunday, October 25', 'Monday, October 26']) {
      expect(cell(name)).toHaveAttribute('data-band', 'mid')
      expect(cell(name)).toHaveClass('bg-primary-tint')
    }
    expect(cell('Wednesday, October 28')).not.toHaveAttribute('data-band')
  })

  it('has no band for one day', () => {
    render(<Picker start="2026-10-23" end="2026-10-23" />)
    expect(day('Friday, October 23').closest('td')).not.toHaveAttribute('data-band')
    expect(day('Friday, October 23')).toHaveClass('bg-primary')
  })

  it('marks the chosen days as selected for assistive technology', () => {
    render(<Picker start="2026-10-23" end="2026-10-27" />)
    expect(day('Friday, October 23').closest('td')).toHaveAttribute('aria-selected', 'true')
    expect(day('Saturday, October 24').closest('td')).toHaveAttribute('aria-selected', 'true')
    expect(day('Wednesday, October 28').closest('td')).not.toHaveAttribute('aria-selected', 'true')
  })

  it('extends the band to the day under the pointer while the last day is being picked', async () => {
    const user = userEvent.setup()
    render(<Picker />)
    await user.click(day('Friday, October 23'))
    await user.hover(day('Tuesday, October 27'))
    const cell = (name: string) => day(name).closest('td')!
    expect(cell('Saturday, October 24')).toHaveAttribute('data-band', 'mid')
    expect(cell('Tuesday, October 27')).toHaveAttribute('data-band', 'end')
    await user.unhover(day('Tuesday, October 27'))
    expect(cell('Saturday, October 24')).not.toHaveAttribute('data-band')
  })

  it('draws a dot under a holiday', async () => {
    const user = userEvent.setup()
    render(<Picker />)
    await user.click(screen.getByRole('button', { name: 'Next month' }))
    const holiday = screen.getByRole('button', { name: /Thanksgiving/ })
    expect(holiday.querySelector('[data-slot="holiday-dot"]')).not.toBeNull()
    expect(day('Wednesday, November 25').querySelector('[data-slot="holiday-dot"]')).toBeNull()
  })

  it('shows the holiday’s name in a tooltip on keyboard focus', async () => {
    const user = userEvent.setup()
    render(<Picker />)
    await user.click(screen.getByRole('button', { name: 'Next month' }))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    await act(async () => {
      screen.getByRole('button', { name: /Thanksgiving/ }).focus()
    })
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Thanksgiving, company holiday')
  })

  it('shows the holiday’s name in a tooltip on hover', async () => {
    const user = userEvent.setup()
    render(<Picker />)
    await user.click(screen.getByRole('button', { name: 'Next month' }))
    await user.hover(screen.getByRole('button', { name: /Thanksgiving/ }))
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Thanksgiving, company holiday')
  })
})

describe('DatePicker limits', () => {
  it('cannot go to a month before the first allowed day', async () => {
    const onChange = vi.fn<(selection: DatePickerSelection) => void>()
    const user = userEvent.setup()
    render(<Picker onChange={onChange} />)
    const previous = screen.getByRole('button', { name: 'Previous month' })
    expect(previous).toHaveAttribute('aria-disabled', 'true')
    await user.click(previous)
    expect(screen.getByRole('grid', { name: 'October 2026' })).toBeInTheDocument()
  })

  it('goes back a month when the first allowed day is earlier', async () => {
    const user = userEvent.setup()
    render(<Picker minDate="2026-09-20" />)
    const previous = screen.getByRole('button', { name: 'Previous month' })
    expect(previous).not.toHaveAttribute('aria-disabled', 'true')
    await user.click(previous)
    expect(screen.getByRole('grid', { name: 'September 2026' })).toBeInTheDocument()
    expect(previous).toHaveAttribute('aria-disabled', 'true')
  })

  it('lets sick time reach back exactly to its first day', async () => {
    const user = userEvent.setup()
    render(
      <Picker minDate="2026-09-20" pastLabel="Sick time can go back 30 days, to September 20" />,
    )
    expect(screen.getByText('Sick time can go back 30 days, to September 20')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Previous month' }))
    expect(
      screen.getByRole('button', { name: 'Sunday, September 20, not on your schedule' }),
    ).not.toHaveAttribute('aria-disabled')
    expect(
      screen.getByRole('button', {
        name: 'Saturday, September 19, not on your schedule, not available',
      }),
    ).toHaveAttribute('aria-disabled', 'true')
  })

  it('cannot go past the month of the last allowed day', async () => {
    const user = userEvent.setup()
    render(<Picker maxDate="2026-11-10" />)
    await user.click(screen.getByRole('button', { name: 'Next month' }))
    expect(screen.getByRole('button', { name: 'Next month' })).toHaveAttribute(
      'aria-disabled',
      'true',
    )
    await user.click(screen.getByRole('button', { name: 'Next month' }))
    expect(screen.getByRole('grid', { name: 'November 2026' })).toBeInTheDocument()
  })
})

describe('DatePicker size', () => {
  it('has 44 px cells holding 40 px days', () => {
    render(<Picker />)
    const button = day('Wednesday, October 21')
    expect(button).toHaveClass('size-10')
    expect(button.closest('td')).toHaveClass('h-11')
  })

  it('lays the weeks out in seven equal columns that fill the width', () => {
    render(<Picker />)
    expect(grid()).toHaveClass('w-full', 'table-fixed')
    expect(within(grid()).getAllByRole('columnheader')).toHaveLength(7)
  })

  describe('DatePicker, Escape and a holiday tooltip', () => {
    it('closes only the tooltip on the first Escape, and the picker on the next', async () => {
      const onDone = vi.fn<() => void>()
      const user = userEvent.setup()
      render(<Picker onDone={onDone} />)
      await user.click(screen.getByRole('button', { name: 'Next month' }))
      await act(async () => {
        screen.getByRole('button', { name: /Thanksgiving/ }).focus()
      })
      expect(await screen.findByRole('tooltip')).toBeInTheDocument()
      await user.keyboard('{Escape}')
      expect(onDone).not.toHaveBeenCalled()
      expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
      await user.keyboard('{Escape}')
      expect(onDone).toHaveBeenCalledOnce()
    })
  })

  describe('DatePicker, a range in progress when the earliest day moves', () => {
    it('drops a start that is before the new earliest day', async () => {
      const onChange = vi.fn<(selection: DatePickerSelection) => void>()
      const user = userEvent.setup()
      const view = (minDate: string) => <Picker minDate={minDate} onChange={onChange} />
      const { rerender } = render(view('2026-09-20'))
      await user.click(day('Monday, October 5'))
      expect(onChange).toHaveBeenLastCalledWith({ start: '2026-10-05', end: '2026-10-05' })
      // The type switches to PTO: nothing before today can be picked, and the old start can't end a range.
      rerender(view(TODAY))
      await user.click(day('Thursday, October 22'))
      expect(onChange).toHaveBeenLastCalledWith({ start: '2026-10-22', end: '2026-10-22' })
    })
  })

  describe('DatePicker, aria-selected', () => {
    const cell = (name: string) => day(name).closest('td')!

    it('does not announce a day as selected just because the preview passes over it', async () => {
      const user = userEvent.setup()
      render(<Picker />)
      await user.click(day('Thursday, October 22'))
      await user.hover(day('Saturday, October 24'))
      // The band is drawn through the 23rd, but only the chosen days are selected.
      expect(cell('Friday, October 23')).toHaveAttribute('data-band', 'mid')
      expect(cell('Friday, October 23')).not.toHaveAttribute('aria-selected')
    })

    it('announces the days inside a chosen range as selected', async () => {
      const user = userEvent.setup()
      render(<Picker />)
      await user.click(day('Thursday, October 22'))
      await user.click(day('Saturday, October 24'))
      expect(cell('Friday, October 23')).toHaveAttribute('aria-selected', 'true')
    })
  })

  describe('DatePicker, the grid’s one tab stop', () => {
    it('is never a day that can not be picked, after paging away and back', async () => {
      const user = userEvent.setup()
      // Nothing after October 10 can be picked, though today is the 20th.
      render(<Picker minDate="2026-09-01" maxDate="2026-10-10" />)
      await user.click(screen.getByRole('button', { name: 'Previous month' }))
      await user.click(day('Tuesday, September 15'))
      await user.click(screen.getByRole('button', { name: 'Next month' }))
      const stops = [...document.querySelectorAll<HTMLElement>('[data-day][tabindex="0"]')]
      expect(stops).toHaveLength(1)
      expect(stops[0]).not.toHaveAttribute('aria-disabled', 'true')
    })
  })

  describe('DatePicker, the tab stop and a start before the earliest day', () => {
    it('is not the selection’s start when that day is no longer allowed', () => {
      render(<Picker start="2026-10-15" minDate="2026-10-22" />)
      const stops = [...document.querySelectorAll<HTMLElement>('[data-day][tabindex="0"]')]
      expect(stops).toHaveLength(1)
      expect(stops[0]).not.toHaveAttribute('aria-disabled', 'true')
    })
  })

  describe('DatePicker, the tab stop when the earliest day moves later', () => {
    it('leaves a focus day that has become unavailable, unless focus is on it', () => {
      const view = (minDate: string) => <Picker start="2026-10-15" minDate={minDate} />
      const { rerender } = render(view('2026-09-20'))
      rerender(view('2026-10-22'))
      const stops = [...document.querySelectorAll<HTMLElement>('[data-day][tabindex="0"]')]
      expect(stops).toHaveLength(1)
      expect(stops[0]).not.toHaveAttribute('aria-disabled', 'true')
    })
  })

  it('keeps the tab stop on a disabled day that has focus, so the arrow keys can pass over it', async () => {
    const user = userEvent.setup()
    render(<Picker />)
    await user.click(day('Tuesday, October 20'))
    await user.keyboard('{ArrowLeft}')
    const focused = day('Monday, October 19')
    expect(focused).toHaveFocus()
    expect(focused).toHaveAttribute('tabindex', '0')
  })
})
