import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { CalendarDay } from './calendar-day'
import {
  WEEKDAY_NAMES,
  addDays,
  addMonths,
  columnOf,
  firstOfMonth,
  isoWeekday,
  lastOfMonth,
  monthGrid,
  monthOf,
  monthTitle,
  shiftMonth,
  type CalendarMonth,
} from './dates'
import { iconButtonClass } from './field-parts'
import { dayLabel, pickerHint, timeOffCopy } from './labels'

type Holiday = { day: string; name: string }

/** The chosen days. A single day has the same `start` and `end`. */
type DatePickerSelection = { start: string; end: string }

type DatePickerProps = {
  /** The id the Dates field's `aria-controls` points at. */
  id: string
  /** Today in the location's timezone, "YYYY-MM-DD". */
  today: string
  /** The earliest day that can be picked: today for PTO, 30 days back for sick time. */
  minDate: string
  /** The latest day that can be picked, when there is one. */
  maxDate?: string
  /** The weekdays the person works, 1 for Monday through 7 for Sunday. */
  scheduledWeekdays: number[]
  holidays: Holiday[]
  start?: string
  end?: string
  /** The legend's last line: why some days are struck through. */
  pastLabel: string
  onChange: (selection: DatePickerSelection) => void
  /** Done or Escape. The parent closes the picker and returns focus to the Dates field. */
  onDone: () => void
  className?: string
}

const monthIndex = ({ year, month }: CalendarMonth) => year * 12 + month

const navButton = cn(
  iconButtonClass,
  'aria-disabled:cursor-not-allowed aria-disabled:text-disabled-fg aria-disabled:hover:bg-transparent',
)

// The legend swatch's 4 px corner is the design's; no radius token is 4 px (`rounded-xs` is 6).
const swatch = 'flex size-3.5 flex-none items-center justify-center rounded-[4px]'

/**
 * The date picker (DatePicker.jsx), inline under the Dates field. A month grid with one tab stop
 * (roving tabindex): arrows move by day, Page Up and Page Down by month (same date, clamped), Home
 * and End to the week's ends, Enter or Space selects, Escape or Done closes.
 *
 * The first day chosen starts a range that is already one day. A later day ends it, a day before
 * the start restarts it, and Done keeps one day. Days that can't be picked stay focusable
 * (`aria-disabled`) so the arrow keys can cross them; days off the person's schedule can be
 * picked, since they are only skipped. Holiday names show in a tooltip on hover and focus.
 *
 * Everything is plain "YYYY-MM-DD" strings. The picker owns the month on show and the focused day;
 * the parent owns the selection.
 */
function DatePicker({
  id,
  today,
  minDate,
  maxDate,
  scheduledWeekdays,
  holidays,
  start,
  end,
  pastLabel,
  onChange,
  onDone,
  className,
}: DatePickerProps) {
  const root = useRef<HTMLDivElement>(null)
  const pendingFocus = useRef<string | null>(null)
  const clampedToday = today < minDate ? minDate : maxDate && today > maxDate ? maxDate : today
  const isDisabled = (day: string) => day < minDate || (maxDate !== undefined && day > maxDate)
  // A start that can't be picked (the type switched and the earliest day moved) doesn't lead.
  const lead = start !== undefined && !isDisabled(start) ? start : clampedToday
  const [month, setMonth] = useState<CalendarMonth>(() => monthOf(lead))
  const [focusDay, setFocusDay] = useState(lead)
  // True between the first and the last day of a range, when a click ends it instead of starting
  // another.
  const [picking, setPicking] = useState(false)
  const [gridFocused, setGridFocused] = useState(false)
  const [preview, setPreview] = useState<string | null>(null)
  const titleId = `${id}-title`

  const holidayNames = new Map(holidays.map((holiday) => [holiday.day, holiday.name]))
  const weeks = monthGrid(month)
  const inView = (day: string) =>
    day.startsWith(`${month.year}-${String(month.month + 1).padStart(2, '0')}`)
  const firstEnabled = weeks.flat().find((day) => day !== null && !isDisabled(day))
  // The focus day leads the grid unless it has become unavailable while focus is elsewhere.
  const tabDay =
    inView(focusDay) && (gridFocused || !isDisabled(focusDay))
      ? focusDay
      : start && inView(start) && !isDisabled(start)
        ? start
        : inView(clampedToday)
          ? clampedToday
          : (firstEnabled ?? weeks.flat().find((day) => day !== null))

  // Keyboard moves stay inside the months the limits allow.
  const lowestFocus = firstOfMonth(monthOf(minDate))
  const highestFocus = maxDate ? lastOfMonth(monthOf(maxDate)) : undefined

  // A range in progress belongs to the earliest day it began under: when that moves past the start
  // (the type switched from sick time to PTO), the start can't begin a range any more.
  if (picking && start !== undefined && start < minDate) setPicking(false)
  const inProgress = picking && start !== undefined && start >= minDate
  const rangeEnd =
    inProgress && preview !== null && start !== undefined && preview > start ? preview : end
  const hasRange = start !== undefined && rangeEnd !== undefined && start !== rangeEnd

  function bandOf(day: string): 'start' | 'mid' | 'end' | undefined {
    if (!hasRange || start === undefined || rangeEnd === undefined) return undefined
    if (day === start) return 'start'
    if (day === rangeEnd) return 'end'
    return day > start && day < rangeEnd ? 'mid' : undefined
  }

  // Focus moves after the render that shows the day, since it may be in another month.
  useEffect(() => {
    const target = pendingFocus.current
    if (target === null) return
    pendingFocus.current = null
    root.current?.querySelector<HTMLElement>(`[data-day="${target}"]`)?.focus()
  })

  function choose(day: string) {
    setFocusDay(day)
    if (isDisabled(day)) return
    // The old preview belongs to the range that is ending or being replaced.
    setPreview(null)
    if (inProgress && start !== undefined && day >= start) {
      onChange({ start, end: day })
      setPicking(false)
    } else {
      onChange({ start: day, end: day })
      setPicking(true)
    }
  }

  function moveTo(next: string) {
    if (next < lowestFocus || (highestFocus !== undefined && next > highestFocus)) return
    pendingFocus.current = next
    setFocusDay(next)
    setMonth(monthOf(next))
  }

  function onGridKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    // Alt+Left, Cmd+Arrow and the like are the browser's.
    if (event.altKey || event.ctrlKey || event.metaKey) return
    const target = event.target instanceof Element ? event.target.closest('[data-day]') : null
    const day = target?.getAttribute('data-day')
    if (!day) return
    let next: string | null = null
    if (event.key === 'ArrowLeft') next = addDays(day, -1)
    else if (event.key === 'ArrowRight') next = addDays(day, 1)
    else if (event.key === 'ArrowUp') next = addDays(day, -7)
    else if (event.key === 'ArrowDown') next = addDays(day, 7)
    else if (event.key === 'PageUp') next = addMonths(day, -1)
    else if (event.key === 'PageDown') next = addMonths(day, 1)
    else if (event.key === 'Home') next = addDays(day, -columnOf(day))
    else if (event.key === 'End') next = addDays(day, 6 - columnOf(day))
    if (next === null) return
    event.preventDefault()
    moveTo(next)
  }

  function onRootKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'Escape') return
    // A day whose holiday tooltip is open (it has aria-describedby) gives the Escape to the
    // tooltip, which has already closed itself: the picker stays open until the next one.
    const onTipDay =
      event.target instanceof Element && event.target.closest('[data-day][aria-describedby]')
    if (event.defaultPrevented && onTipDay) return
    event.preventDefault()
    onDone()
  }

  const canGoBack = monthIndex(month) > monthIndex(monthOf(minDate))
  const canGoForward = maxDate === undefined || monthIndex(month) < monthIndex(monthOf(maxDate))

  return (
    // Escape from anywhere inside closes the picker: the handler is for keys bubbling up from the
    // buttons and days, not for the container itself.
    // oxlint-disable-next-line jsx-a11y/no-static-element-interactions
    <div
      ref={root}
      id={id}
      data-slot="date-picker"
      onKeyDown={onRootKeyDown}
      className={cn(
        'rounded-lg border border-border bg-surface-raised px-3 pt-3 pb-3.5 text-ink',
        className,
      )}
    >
      <div className="flex items-center justify-between pb-2 pl-2">
        <div
          id={titleId}
          aria-live="polite"
          className="m-0 text-body font-semibold text-ink tabular-nums"
        >
          {monthTitle(month)}
        </div>
        <div className="flex gap-1">
          <button
            type="button"
            aria-label={timeOffCopy.previousMonth}
            aria-disabled={!canGoBack || undefined}
            onClick={() => canGoBack && setMonth(shiftMonth(month, -1))}
            className={navButton}
          >
            <ChevronLeft aria-hidden="true" className="size-4" />
          </button>
          <button
            type="button"
            aria-label={timeOffCopy.nextMonth}
            aria-disabled={!canGoForward || undefined}
            onClick={() => canGoForward && setMonth(shiftMonth(month, 1))}
            className={navButton}
          >
            <ChevronRight aria-hidden="true" className="size-4" />
          </button>
        </div>
      </div>
      {/* A table with the grid role: its cells become gridcells, and the day buttons hold the focus. */}
      {/* oxlint-disable-next-line jsx-a11y/interactive-supports-focus */}
      <table
        // oxlint-disable-next-line jsx-a11y/no-noninteractive-element-to-interactive-role
        role="grid"
        aria-multiselectable="true"
        aria-labelledby={titleId}
        onKeyDown={onGridKeyDown}
        onMouseLeave={() => setPreview(null)}
        onBlur={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) setGridFocused(false)
        }}
        className="w-full table-fixed border-collapse"
      >
        <thead>
          <tr>
            {WEEKDAY_NAMES.map((name) => (
              <th
                key={name}
                scope="col"
                aria-label={name}
                className="h-7 p-0 text-caption font-regular text-ink-muted"
              >
                {name.slice(0, 2)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {weeks.map((week) => (
            <tr key={week.find((day) => day !== null) ?? 'empty'}>
              {week.map((day, column) => {
                // oxlint-disable-next-line jsx-a11y/control-has-associated-label
                if (day === null) return <td key={`pad-${column}`} className="h-11 p-0" />
                const disabled = isDisabled(day)
                const holiday = holidayNames.get(day)
                const off = !scheduledWeekdays.includes(isoWeekday(day))
                const band = bandOf(day)
                return (
                  <CalendarDay
                    key={day}
                    day={day}
                    label={dayLabel({ day, holiday, off, today: day === today, disabled })}
                    holiday={holiday}
                    off={off}
                    today={day === today}
                    disabled={disabled}
                    selected={day === start || day === end}
                    band={band}
                    chosen={start !== undefined && end !== undefined && day >= start && day <= end}
                    tabIndex={day === tabDay ? 0 : -1}
                    onSelect={choose}
                    onPreview={(hovered) => picking && !isDisabled(hovered) && setPreview(hovered)}
                    onFocusDay={(focused) => {
                      setGridFocused(true)
                      setFocusDay(focused)
                      if (picking && !isDisabled(focused)) setPreview(focused)
                    }}
                  />
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-2 border-t border-border-subtle px-2 pt-2.5 text-caption text-ink-muted">
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className={cn(swatch, 'bg-surface-hover')} />
          {timeOffCopy.legendOff}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className={cn(swatch, 'items-end')}>
            <span className="mb-0.5 size-1 rounded-full bg-ink-nav" />
          </span>
          {timeOffCopy.legendHoliday}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className={cn(swatch, 'border border-input-border')} />
          {timeOffCopy.legendToday}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className={cn(swatch, 'text-[11px] leading-[14px] text-disabled-fg line-through')}
          >
            8
          </span>
          {pastLabel}
        </span>
      </div>
      <div className="mt-3 flex items-center justify-between gap-3 pr-1 pl-2">
        <output className="m-0 block text-small text-pretty">
          {pickerHint({ start, end, inProgress })}
        </output>
        <Button variant="secondary" size="sm" onClick={onDone}>
          {timeOffCopy.done}
        </Button>
      </div>
    </div>
  )
}

export { DatePicker }
export type { DatePickerProps, DatePickerSelection, Holiday }
