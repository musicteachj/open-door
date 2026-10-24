import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { holidayTip } from './labels'

type CalendarDayProps = {
  /** "YYYY-MM-DD". */
  day: string
  /** The accessible name: the date and every mark it carries. */
  label: string
  /** The holiday's name; the day gets a dot and a tooltip. */
  holiday?: string
  /** Not on the person's schedule: shaded, still selectable. */
  off?: boolean
  today?: boolean
  selected?: boolean
  /** Can't be picked: struck through, still focusable so the arrow keys can pass over it. */
  disabled?: boolean
  /** Inside the chosen range (from the real selection, never the hover preview). */
  chosen?: boolean
  /** Where the day sits in a range, for the tint behind it. */
  band?: 'start' | 'mid' | 'end'
  /** 0 for the one day that is the grid's tab stop, -1 for the rest. */
  tabIndex: 0 | -1
  onSelect: (day: string) => void
  onPreview: (day: string) => void
  onFocusDay: (day: string) => void
}

const BAND_CLASS = {
  start: 'bg-[linear-gradient(to_right,transparent_50%,var(--color-primary-tint)_50%)]',
  mid: 'bg-primary-tint',
  end: 'bg-[linear-gradient(to_left,transparent_50%,var(--color-primary-tint)_50%)]',
} as const

/**
 * One day in the picker (CalendarDay in DatePicker.jsx): a 44 px cell holding a 40 px day button.
 * The states are chosen here, not with attribute variants, so two marks that meet (a holiday that
 * is also off the schedule) never fight over the same property.
 */
function CalendarDay({
  day,
  label,
  holiday,
  off = false,
  today = false,
  selected = false,
  disabled = false,
  band,
  chosen = false,
  tabIndex,
  onSelect,
  onPreview,
  onFocusDay,
}: CalendarDayProps) {
  const button = (
    <button
      type="button"
      data-day={day}
      aria-label={label}
      aria-disabled={disabled || undefined}
      tabIndex={tabIndex}
      onClick={() => onSelect(day)}
      onMouseEnter={() => onPreview(day)}
      onFocus={() => onFocusDay(day)}
      className={cn(
        'relative size-10 rounded-md border-0 bg-transparent text-ui font-regular text-ink tabular-nums transition-colors outline-none',
        'focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-focus-ring focus-visible:outline-solid',
        disabled
          ? 'cursor-not-allowed text-disabled-fg line-through decoration-1'
          : cn(
              'cursor-pointer',
              selected
                ? 'bg-primary font-semibold text-on-primary'
                : cn(
                    'hover:bg-neutral-hover',
                    off && !(band === 'mid') && 'bg-surface-hover text-ink-muted',
                    off && band === 'mid' && 'text-ink-muted',
                    today && 'font-semibold shadow-[inset_0_0_0_1px_var(--color-input-border)]',
                  ),
            ),
      )}
    >
      {day.slice(8).replace(/^0/, '')}
      {holiday && (
        <span
          data-slot="holiday-dot"
          aria-hidden="true"
          className={cn(
            'absolute bottom-[5px] left-1/2 -ml-0.5 size-1 rounded-full',
            selected ? 'bg-on-primary' : 'bg-ink-nav',
          )}
        />
      )}
    </button>
  )
  return (
    <td
      data-band={band}
      aria-selected={selected || chosen || undefined}
      className={cn('relative h-11 p-0 text-center', band && BAND_CLASS[band])}
    >
      {holiday ? (
        <Tooltip>
          <TooltipTrigger asChild>{button}</TooltipTrigger>
          <TooltipContent>{holidayTip(holiday)}</TooltipContent>
        </Tooltip>
      ) : (
        button
      )}
    </td>
  )
}

export { CalendarDay }
export type { CalendarDayProps }
