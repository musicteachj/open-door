import { Calendar, ChevronDown, ChevronUp } from 'lucide-react'
import { useId, type Ref } from 'react'
import { cn } from '@/lib/utils'
import { FieldError, fieldLabelClass } from './field-parts'
import { longRange, shortRange } from './dates'
import { timeOffCopy } from './labels'

type DateFieldProps = {
  /** The first day, as "YYYY-MM-DD". With no `start` the field shows its placeholder. */
  start?: string
  /** The last day; leave it out for one day. */
  end?: string
  open?: boolean
  /** The id of the picker this field opens. */
  controls?: string
  error?: string
  disabled?: boolean
  onToggle: () => void
  /** The button, so the parent can return focus to it when the picker closes. */
  ref?: Ref<HTMLButtonElement>
  className?: string
}

/**
 * The Dates field (DateField.jsx): a button that opens the picker under it. It shows the short form
 * ("Wed, Nov 25 to Fri, Nov 27") so a range fits on one line, and is named by its label and the
 * full form ("Wednesday, November 25 to Friday, November 27"), since the short form is
 * abbreviated.
 */
function DateField({
  start,
  end,
  open = false,
  controls,
  error,
  disabled = false,
  onToggle,
  ref,
  className,
}: DateFieldProps) {
  const id = useId()
  const labelId = `${id}-label`
  const valueId = `${id}-value`
  const errorId = `${id}-error`
  const shortForm = start ? shortRange(start, end ?? start) : null
  const fullForm = start ? longRange(start, end ?? start) : timeOffCopy.datesPlaceholder
  const Chevron = open ? ChevronUp : ChevronDown
  return (
    <div data-slot="date-field" className={cn('flex flex-col gap-2', className)}>
      <span id={labelId} className={fieldLabelClass}>
        {timeOffCopy.datesLabel}
      </span>
      <button
        ref={ref}
        type="button"
        aria-expanded={open}
        aria-controls={controls}
        aria-labelledby={`${labelId} ${valueId}`}
        data-invalid={error ? '' : undefined}
        aria-describedby={error ? errorId : undefined}
        disabled={disabled}
        onClick={onToggle}
        className={cn(
          'group flex h-11 w-full cursor-pointer items-center gap-2.5 rounded-md border border-input-border bg-surface-raised px-3 text-left text-body text-ink',
          'transition-[border-color] outline-none',
          'enabled:hover:border-input-border-hover',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus-ring focus-visible:outline-solid',
          'aria-expanded:border-primary aria-expanded:shadow-focus-halo',
          'data-[invalid]:border-danger',
          'disabled:cursor-not-allowed disabled:border-disabled-bg disabled:bg-disabled-bg disabled:text-disabled-fg',
        )}
      >
        <Calendar
          aria-hidden="true"
          className="size-4 flex-none text-ink-muted group-disabled:text-disabled-fg"
        />
        <span
          aria-hidden="true"
          className={cn(
            'min-w-0 flex-1 truncate tabular-nums',
            shortForm === null && 'text-ink-placeholder',
          )}
        >
          {shortForm ?? timeOffCopy.datesPlaceholder}
        </span>
        <span id={valueId} className="sr-only">
          {fullForm}
        </span>
        <Chevron
          aria-hidden="true"
          className="size-4 flex-none text-ink-muted group-disabled:text-disabled-fg"
        />
      </button>
      {error && <FieldError id={errorId}>{error}</FieldError>}
    </div>
  )
}

export { DateField }
export type { DateFieldProps }
