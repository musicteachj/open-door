import { Minus, Plus } from 'lucide-react'
import { useId } from 'react'
import { cn } from '@/lib/utils'
import { FieldError, fieldHintClass, fieldLabelClass } from './field-parts'
import { timeOffCopy } from './labels'
import { MAX_HOURS, MIN_HOURS, parseHours, wholeNumber } from './parse-hours'

type HoursStepperProps = {
  /** The text in the box. The parent owns it, so a half-typed value is the parent's to see. */
  value: string
  onValueChange: (value: string) => void
  disabled?: boolean
  className?: string
}

// The 42 px heights are the specimen's border-box value: the 44 px box less its 1 px border.
const stepButton = cn(
  'flex h-[42px] w-11 cursor-pointer items-center justify-center border-0 bg-transparent text-ink',
  'enabled:hover:bg-neutral-hover enabled:active:bg-border-subtle',
  'focus-visible:-outline-offset-2 focus-visible:outline-2 focus-visible:outline-focus-ring focus-visible:outline-solid',
  'disabled:cursor-not-allowed disabled:text-disabled-fg',
)

/**
 * Hours for a part-day request (HoursStepper.jsx): a box with minus and plus, 1 to 8. Anything in
 * the box that is not a whole number from 1 to 8 shows the error, which is announced. The buttons
 * stop at the ends; from a bad value they bring it back into range.
 */
function HoursStepper({ value, onValueChange, disabled = false, className }: HoursStepperProps) {
  const id = useId()
  const hintId = `${id}-hint`
  const errorId = `${id}-error`
  const hours = parseHours(value)
  const invalid = hours === null
  // A number outside the range still steps back in: from 12, Fewer hours goes to 8.
  const whole = wholeNumber(value)

  function step(delta: number) {
    const next = Math.max(MIN_HOURS, Math.min(MAX_HOURS, (whole ?? 0) + delta))
    onValueChange(String(next))
  }

  return (
    <div data-slot="hours-stepper" className={cn('flex flex-col gap-1.5', className)}>
      <label htmlFor={id} className={fieldLabelClass}>
        {timeOffCopy.hoursLabel}
      </label>
      <div className="flex items-center gap-3">
        <div
          data-invalid={invalid ? '' : undefined}
          data-disabled={disabled ? '' : undefined}
          className={cn(
            'inline-flex h-11 items-center overflow-hidden rounded-md border border-input-border bg-surface-raised transition-[border-color]',
            'focus-within:border-focus-ring focus-within:shadow-focus-halo hover:border-input-border-hover',
            'data-[invalid]:border-danger',
            'data-[disabled]:border-disabled-bg data-[disabled]:bg-disabled-bg data-[disabled]:shadow-none',
          )}
        >
          <button
            type="button"
            aria-label={timeOffCopy.fewerHours}
            disabled={disabled || (whole !== null && whole <= MIN_HOURS)}
            onClick={() => step(-1)}
            className={stepButton}
          >
            <Minus aria-hidden="true" className="size-4" />
          </button>
          <input
            id={id}
            type="text"
            inputMode="numeric"
            maxLength={4}
            value={value}
            disabled={disabled}
            aria-invalid={invalid ? true : undefined}
            aria-describedby={invalid ? `${hintId} ${errorId}` : hintId}
            onChange={(event) => onValueChange(event.target.value)}
            className="h-[42px] w-14 border-0 border-x border-solid border-x-border-subtle bg-transparent text-center text-body font-semibold text-ink tabular-nums outline-none disabled:text-disabled-fg"
          />
          <button
            type="button"
            aria-label={timeOffCopy.moreHours}
            disabled={disabled || (whole !== null && whole >= MAX_HOURS)}
            onClick={() => step(1)}
            className={stepButton}
          >
            <Plus aria-hidden="true" className="size-4" />
          </button>
        </div>
        <span id={hintId} className={fieldHintClass}>
          {timeOffCopy.hoursHint}
        </span>
      </div>
      {invalid && <FieldError id={errorId}>{timeOffCopy.hoursError}</FieldError>}
    </div>
  )
}

export { HoursStepper }
export type { HoursStepperProps }
