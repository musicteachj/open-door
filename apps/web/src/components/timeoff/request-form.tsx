import { Info, X } from 'lucide-react'
import { useCallback, useId, useRef, useState } from 'react'
import type { CheckOut } from '@/api/generated'
import { BottomSheet, SheetTitle } from '@/components/ui/bottom-sheet'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import {
  howMuchOptionsFor,
  resolveChoice,
  type HowMuch,
  type LeaveKind,
  type SubmitChoice,
} from './choice'
import { ChoiceGroup } from './choice-group'
import { DateField } from './date-field'
import { DatePicker, type DatePickerProps, type DatePickerSelection } from './date-picker'
import { iconButtonClass } from './field-parts'
import { FormMessage } from './form-message'
import { HoursStepper } from './hours-stepper'
import { formCopy, problemText, timeOffCopy } from './labels'
import { parseHours } from './parse-hours'
import { PreviewBlock } from './preview-block'
import { SegmentedControl } from './segmented-control'

type RequestFormProps = {
  /** A docked, non-modal panel beside the page (wide window) or a modal bottom sheet (narrow). */
  docked: boolean
  /** The id the "Request time off" button's `aria-controls` points at (the docked panel). */
  id?: string
  /** Move focus to the title when the form opens (the default). A gallery turns it off. */
  autoFocusTitle?: boolean
  type: LeaveKind
  onTypeChange: (type: LeaveKind) => void
  start?: string
  end?: string
  onDatesChange: (selection: DatePickerSelection) => void
  /** What the date picker marks: today, the earliest day, the schedule, the holidays. */
  calendar: Omit<DatePickerProps, 'id' | 'start' | 'end' | 'onChange' | 'onDone' | 'className'>
  /** "How much", for a single day: PTO is full or half, sick time is full or some hours. */
  howMuch: HowMuch
  onHowMuchChange: (howMuch: HowMuch) => void
  /** The text in the hours box. */
  hours: string
  onHoursChange: (hours: string) => void
  /** What `POST /time-off/check` said for the picked days. Null before anything is picked. */
  check: CheckOut | null
  /** The manager who reviews PTO, named in the footer. */
  approverName?: string | null
  /** The current year, so sick time in another year names its year. */
  thisYear?: number
  /**
   * True while a check for the current type, dates, how much, and hours is in flight. The page
   * must pass the check for the current inputs and set this from the moment they change until
   * that check arrives: the old figures are shown muted and Submit waits, so a request is never
   * sent beside figures that belong to different dates.
   */
  checking?: boolean
  submitting?: boolean
  /** What a failed send came back with: the server's refusal or a plain "try again". Shown as an alert. */
  submitError?: string | null
  /** The check for the current inputs failed: the preview says so, and Submit stays off. */
  previewFailed?: boolean
  /** Asks for the same check again. With it, the failed-preview message offers "Try again". */
  onRetryPreview?: () => void
  /** What to send for how much, matching what the form shows: Full day for a range, and the hours only for "Some hours". */
  onSubmit: (choice: SubmitChoice) => void
  /** Close and Cancel. The page returns focus to "Request time off". */
  onClose: () => void
  className?: string
}

/**
 * The request form (docs/design/screens/08-time-off), driven entirely by props: the page owns the
 * values and calls the check and submit routes. A fixed header with Close, a body that scrolls (the
 * type, the dates with their inline picker, how much, "What this uses", and the messages), and a
 * fixed footer (the approver note and the buttons).
 *
 * Opening moves focus to the title. The date picker keeps the Escape key for itself, so in the
 * phone's sheet it closes only the picker.
 */
function RequestForm({
  docked,
  id,
  autoFocusTitle = true,
  type,
  onTypeChange,
  start,
  end,
  onDatesChange,
  calendar,
  howMuch,
  onHowMuchChange,
  hours,
  onHoursChange,
  check,
  approverName,
  thisYear,
  checking = false,
  submitting = false,
  submitError = null,
  previewFailed = false,
  onRetryPreview,
  onSubmit,
  onClose,
  className,
}: RequestFormProps) {
  const titleId = useId()
  const pickerId = useId()
  // Focus lands on the title the moment it is in the page. A callback ref is used because the
  // sheet's content mounts a render after this component, so a mount effect would find nothing.
  const focusTitle = useCallback(
    (node: HTMLHeadingElement | null) => {
      if (autoFocusTitle) node?.focus()
    },
    [autoFocusTitle],
  )
  const dateFieldRef = useRef<HTMLButtonElement>(null)
  const [pickerOpen, setPickerOpen] = useState(false)

  // While the request is being sent nothing closes the form: not Close, Cancel, Escape, or a swipe.
  function close() {
    if (!submitting) onClose()
  }

  // A "how much" the new type does not offer (Some hours for PTO, Half day for sick time) goes
  // back to Full day, so the form never holds a pair the type cannot submit.
  function changeType(value: string) {
    const next = value as LeaveKind
    if (!howMuchOptionsFor(next).some((option) => option.value === howMuch)) onHowMuchChange('full')
    onTypeChange(next)
  }

  // A range has no "how much": it goes back to Full day, so the form never keeps a half day for it.
  function changeDates(selection: DatePickerSelection) {
    if (selection.start !== selection.end && howMuch !== 'full') onHowMuchChange('full')
    onDatesChange(selection)
  }

  function closePicker() {
    setPickerOpen(false)
    dateFieldRef.current?.focus()
  }

  // The dates can't change while the request is on its way, so an open picker closes for good
  // (it stays closed if the send fails).
  if (submitting && pickerOpen) setPickerOpen(false)
  const sick = type === 'sick'
  const single = start !== undefined && start === end
  const problems = check?.problems ?? []
  const refused = problems.length > 0
  // What the form reports is what it shows: a range is always Full day, and a how-much the type
  // does not offer is Full day too. Hours count only for "Some hours" on one sick day.
  const howMuchOptions = howMuchOptionsFor(type)
  const effectiveChoice = resolveChoice(type, start, end, howMuch, hours)
  const hoursInvalid = sick && single && howMuch === 'hours' && parseHours(hours) === null
  const cannotSubmit =
    start === undefined || check === null || !check.ok || refused || hoursInvalid || checking

  const title = {
    ref: focusTitle,
    tabIndex: -1,
    className: 'm-0 text-h2 text-ink outline-none',
  }

  const body = (
    <div
      data-slot="request-form"
      className={cn('flex h-full min-h-0 flex-col bg-surface-raised text-ink', className)}
    >
      <header className="flex flex-none items-center justify-between gap-3 border-b border-border-subtle px-6 py-4">
        {docked ? (
          <h2 id={titleId} {...title}>
            {formCopy.title}
          </h2>
        ) : (
          <SheetTitle {...title}>{formCopy.title}</SheetTitle>
        )}
        <button
          type="button"
          aria-label={formCopy.close}
          disabled={submitting}
          onClick={close}
          className={cn(
            iconButtonClass,
            'disabled:cursor-not-allowed disabled:text-disabled-fg disabled:hover:bg-transparent',
          )}
        >
          <X aria-hidden="true" className="size-4" />
        </button>
      </header>
      <div
        data-slot="request-form-body"
        className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-6 py-5"
      >
        <SegmentedControl
          label={timeOffCopy.typeLabel}
          options={[
            { value: 'pto', label: timeOffCopy.typePto },
            { value: 'sick', label: timeOffCopy.typeSick },
          ]}
          value={type}
          onValueChange={changeType}
          disabled={submitting}
        />
        {/* The picker closes itself on Escape from inside it. This closes it from the field. */}
        {/* oxlint-disable-next-line jsx-a11y/no-static-element-interactions */}
        <div
          data-slot="date-section"
          className="flex flex-col gap-2"
          onKeyDown={(event) => {
            if (event.key !== 'Escape' || !pickerOpen) return
            if (
              event.target instanceof Element &&
              event.target.closest('[data-slot="date-picker"]')
            ) {
              return
            }
            event.preventDefault()
            closePicker()
          }}
        >
          <DateField
            ref={dateFieldRef}
            start={start}
            end={end}
            open={pickerOpen}
            controls={pickerOpen ? pickerId : undefined}
            disabled={submitting}
            onToggle={() => setPickerOpen((open) => !open)}
          />
          {pickerOpen && (
            <DatePicker
              id={pickerId}
              {...calendar}
              start={start}
              end={end}
              onChange={changeDates}
              onDone={closePicker}
            />
          )}
        </div>
        {single && (
          <ChoiceGroup
            label={timeOffCopy.howMuchLabel}
            options={howMuchOptions}
            value={howMuch}
            onValueChange={(value) => onHowMuchChange(value as HowMuch)}
            disabled={submitting}
          />
        )}
        {sick && single && howMuch === 'hours' && (
          <HoursStepper value={hours} onValueChange={onHoursChange} disabled={submitting} />
        )}
        {check === null || start === undefined ? (
          <PreviewBlock
            type={type}
            countedDays={[]}
            skippedDays={[]}
            amountLabel={null}
            draws={[]}
            rules={[]}
            empty
          />
        ) : (
          <PreviewBlock
            type={type}
            countedDays={check.countedDays}
            skippedDays={check.skippedDays}
            overlappingDays={check.overlappingDays}
            amountLabel={check.amountLabel}
            draws={check.draws}
            rules={check.rules}
            refused={refused}
            thisYear={thisYear}
            muted={checking}
            busy={checking}
          />
        )}
        {!checking && check?.warnings.includes('short-notice') && (
          <FormMessage tone="warning">{formCopy.shortNotice}</FormMessage>
        )}
        {!checking &&
          check &&
          problems.map((problem) => (
            <FormMessage key={problem.code} tone="refusal">
              {problemText(problem, {
                type,
                draws: check.draws,
                amountLabel: check.amountLabel,
                overlappingDays: check.overlappingDays,
                thisYear,
              })}
            </FormMessage>
          ))}
        {previewFailed && !checking && check === null && (
          <FormMessage tone="refusal">
            <span className="flex flex-wrap items-center gap-x-3 gap-y-2">
              {formCopy.previewFailed}
              {onRetryPreview && (
                <Button variant="secondary" size="sm" onClick={onRetryPreview}>
                  {formCopy.tryAgain}
                </Button>
              )}
            </span>
          </FormMessage>
        )}
        {submitError && <FormMessage tone="refusal">{submitError}</FormMessage>}
      </div>
      <footer className="flex flex-none flex-col gap-3 border-t border-border-subtle px-6 py-4">
        {(sick || approverName) && (
          <p className="m-0 flex items-start gap-2 text-small text-ink-muted">
            <Info aria-hidden="true" className="mt-0.5 size-4 flex-none" />
            {sick ? formCopy.sickNote : formCopy.approverNote(approverName ?? '')}
          </p>
        )}
        <div className="flex gap-3">
          <Button
            loading={submitting}
            aria-disabled={submitting || undefined}
            disabled={cannotSubmit && !submitting}
            onClick={() => onSubmit(effectiveChoice)}
            className="max-sm:flex-1"
          >
            {submitting
              ? sick
                ? formCopy.submittingSick
                : formCopy.submittingPto
              : sick
                ? formCopy.submitSick
                : formCopy.submitPto}
          </Button>
          <Button
            variant="secondary"
            disabled={submitting}
            onClick={close}
            className="max-sm:flex-1"
          >
            {formCopy.cancel}
          </Button>
        </div>
      </footer>
    </div>
  )

  if (!docked) {
    return (
      <BottomSheet
        onClose={close}
        // The picker takes Escape for itself: it closes the picker and the sheet stays.
        onEscapeKeyDown={(event) => {
          if (
            pickerOpen &&
            event.target instanceof Element &&
            event.target.closest('[data-slot="date-section"]')
          ) {
            event.preventDefault()
          }
        }}
      >
        {body}
      </BottomSheet>
    )
  }
  return (
    <section
      id={id}
      aria-labelledby={titleId}
      className="h-full min-h-0 w-panel max-w-full border-l border-border-subtle"
    >
      {body}
    </section>
  )
}

export { RequestForm }
export type { HowMuch, SubmitChoice, LeaveKind, RequestFormProps }
