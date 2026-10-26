import { useRef, useState, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogActions,
  AlertDialogCancel,
  AlertDialogConfirm,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { BalanceCard } from '@/components/timeoff/balance-card'
import { ChoiceGroup } from '@/components/timeoff/choice-group'
import { DateField } from '@/components/timeoff/date-field'
import { DatePicker, type DatePickerSelection } from '@/components/timeoff/date-picker'
import { FormMessage } from '@/components/timeoff/form-message'
import { HoursStepper } from '@/components/timeoff/hours-stepper'
import {
  decisionLine,
  halfDayChoice,
  pastLabelSick,
  timeOffCopy,
} from '@/components/timeoff/labels'
import { PreviewBlock } from '@/components/timeoff/preview-block'
import { RequestForm, type HowMuch, type LeaveKind } from '@/components/timeoff/request-form'
import { RequestGroup } from '@/components/timeoff/request-group'
import { RequestRow } from '@/components/timeoff/request-row'
import { SegmentedControl } from '@/components/timeoff/segmented-control'
import { StatusBadge } from '@/components/timeoff/status-badge'
import type { CheckOut } from '@/api/generated'
import { Group, Section } from '../gallery-parts'
import {
  CHECK_CROSS_YEAR_SICK,
  CHECK_HOLIDAY,
  CHECK_LONG_RUNS,
  CHECK_NOT_ENOUGH,
  CHECK_NOTHING_COUNTED,
  CHECK_ONE_DAY,
  CHECK_OVERLAP,
  CHECK_SHORT_NOTICE,
  CHECK_SICK_HOURS,
  CHECK_WEEKEND,
  MARCUS,
  MINE_APPROVED,
  MINE_CANCELED,
  MINE_DENIED,
  MINE_RECORDED,
  MINE_WAITING,
  PTO_BALANCE,
  PTO_BALANCE_CEILING,
  PTO_BALANCE_EMPTY,
  PTO_RULE,
  SICK_RULE,
  SICK_YEAR,
  SICK_YEAR_EMPTY,
  TEAM_APPROVED,
  TEAM_DENIED,
  THIS_YEAR,
  TIME_ZONE,
} from '../fixtures/timeoff'

// The time-off form's parts, each state under a heading with a stable id: Priya Raman's Monday to
// Friday schedule, Oakland's holidays, and today as Tuesday, October 20, 2026 (the design's
// persona). Hover and focus are not drawn: the browser tests hover and focus the real elements.

// The 372 px frames imitate the request form's inner width: its 420 px panel less 24 px of padding
// on each side.
const TODAY = '2026-10-20'
const SICK_EARLIEST = '2026-09-20'
const SCHEDULE = [1, 2, 3, 4, 5]
const HOLIDAYS = [
  { day: '2026-11-26', name: 'Thanksgiving' },
  { day: '2026-12-25', name: 'Christmas Day' },
  { day: '2027-01-01', name: "New Year's Day" },
]

const TYPE_OPTIONS = [
  { value: 'pto', label: timeOffCopy.typePto },
  { value: 'sick', label: timeOffCopy.typeSick },
]
const DAY_OPTIONS = [
  { value: 'full', label: timeOffCopy.fullDay },
  { value: 'half', label: halfDayChoice('4 hours') },
]

function Type({ initial, disabled = false }: { initial: string; disabled?: boolean }) {
  const [value, setValue] = useState(initial)
  return (
    <div className="w-[372px] max-w-full">
      <SegmentedControl
        label={timeOffCopy.typeLabel}
        options={TYPE_OPTIONS}
        value={value}
        onValueChange={setValue}
        disabled={disabled}
      />
    </div>
  )
}

function Choice({ initial, disabled = false }: { initial: string; disabled?: boolean }) {
  const [value, setValue] = useState(initial)
  return (
    <div className="w-[372px] max-w-full">
      <ChoiceGroup
        label={timeOffCopy.howMuchLabel}
        options={DAY_OPTIONS}
        value={value}
        onValueChange={setValue}
        disabled={disabled}
      />
    </div>
  )
}

function Stepper({ initial, disabled = false }: { initial: string; disabled?: boolean }) {
  const [value, setValue] = useState(initial)
  return <HoursStepper value={value} onValueChange={setValue} disabled={disabled} />
}

function Field({
  start,
  end,
  open = false,
  error,
  disabled = false,
}: {
  start?: string
  end?: string
  open?: boolean
  error?: string
  disabled?: boolean
}) {
  const [isOpen, setOpen] = useState(open)
  return (
    <div className="w-[372px] max-w-full">
      <DateField
        start={start}
        end={end}
        open={isOpen}
        error={error}
        disabled={disabled}
        onToggle={() => setOpen(!isOpen)}
      />
    </div>
  )
}

function Picker({
  id,
  minDate,
  pastLabel,
  initial,
}: {
  id: string
  minDate: string
  pastLabel: string
  initial?: DatePickerSelection
}) {
  const [selection, setSelection] = useState<DatePickerSelection | undefined>(initial)
  return (
    <div className="w-[372px] max-w-full">
      <DatePicker
        id={id}
        today={TODAY}
        minDate={minDate}
        scheduledWeekdays={SCHEDULE}
        holidays={HOLIDAYS}
        start={selection?.start}
        end={selection?.end}
        pastLabel={pastLabel}
        onChange={setSelection}
        onDone={() => {}}
      />
    </div>
  )
}

/** A frame for request groups, which hold their own list. */
function GroupFrame({ children }: { children: ReactNode }) {
  return <div className="w-[928px] max-w-full">{children}</div>
}

function Rows({ children }: { children: ReactNode }) {
  return <ul className="m-0 w-[928px] max-w-full list-none p-0">{children}</ul>
}

function Preview({
  check,
  type = 'pto',
  refused = false,
}: {
  check: CheckOut
  type?: 'pto' | 'sick'
  refused?: boolean
}) {
  return (
    <div className="w-[372px] max-w-full">
      <PreviewBlock
        type={type}
        countedDays={check.countedDays}
        skippedDays={check.skippedDays}
        overlappingDays={check.overlappingDays}
        amountLabel={check.amountLabel}
        draws={check.draws}
        rules={check.rules}
        refused={refused}
        thisYear={THIS_YEAR}
      />
    </div>
  )
}

/** The docked request form in a frame as tall as a window, with its picker closed. */
function FormFrame({
  type: initialType = 'pto',
  start: initialStart,
  end: initialEnd,
  howMuch: initialHowMuch = 'full',
  hours: initialHours = '3',
  check,
  submitting = false,
}: {
  type?: LeaveKind
  start: string
  end?: string
  howMuch?: HowMuch
  hours?: string
  check: CheckOut
  submitting?: boolean
}) {
  const [type, setType] = useState<LeaveKind>(initialType)
  const [selection, setSelection] = useState<DatePickerSelection>({
    start: initialStart,
    end: initialEnd ?? initialStart,
  })
  const [howMuch, setHowMuch] = useState<HowMuch>(initialHowMuch)
  const [hours, setHours] = useState(initialHours)
  return (
    <div className="h-[760px] w-panel max-w-full overflow-hidden rounded-lg border border-border">
      <RequestForm
        docked
        autoFocusTitle={false}
        type={type}
        onTypeChange={setType}
        start={selection.start}
        end={selection.end}
        onDatesChange={setSelection}
        calendar={{
          today: TODAY,
          minDate: type === 'sick' ? SICK_EARLIEST : TODAY,
          scheduledWeekdays: SCHEDULE,
          holidays: HOLIDAYS,
          pastLabel: type === 'sick' ? pastLabelSick(30, SICK_EARLIEST) : timeOffCopy.pastLabelPto,
        }}
        halfDayLabel="4 hours"
        howMuch={howMuch}
        onHowMuchChange={setHowMuch}
        hours={hours}
        onHoursChange={setHours}
        check={check}
        approverName={MARCUS.name}
        thisYear={THIS_YEAR}
        submitting={submitting}
        onSubmit={() => {}}
        onClose={() => {}}
      />
    </div>
  )
}

/** The request form as the phone's modal bottom sheet, closed until its button is pressed. */
function SheetDemo() {
  const [open, setOpen] = useState(false)
  const [type, setType] = useState<LeaveKind>('pto')
  const [selection, setSelection] = useState<DatePickerSelection>({
    start: '2026-10-30',
    end: '2026-10-30',
  })
  const [howMuch, setHowMuch] = useState<HowMuch>('full')
  const [hours, setHours] = useState('3')
  const opener = useRef<HTMLButtonElement>(null)
  function close() {
    setOpen(false)
    // The page returns focus to the button that opened the form.
    setTimeout(() => opener.current?.focus(), 0)
  }
  return (
    <>
      <Button ref={opener} variant="secondary" onClick={() => setOpen(true)}>
        Open the request form as a sheet
      </Button>
      {open && (
        <RequestForm
          docked={false}
          type={type}
          onTypeChange={setType}
          start={selection.start}
          end={selection.end}
          onDatesChange={setSelection}
          calendar={{
            today: TODAY,
            minDate: type === 'sick' ? SICK_EARLIEST : TODAY,
            scheduledWeekdays: SCHEDULE,
            holidays: HOLIDAYS,
            pastLabel:
              type === 'sick' ? pastLabelSick(30, SICK_EARLIEST) : timeOffCopy.pastLabelPto,
          }}
          halfDayLabel="4 hours"
          howMuch={howMuch}
          onHowMuchChange={setHowMuch}
          hours={hours}
          onHoursChange={setHours}
          check={CHECK_ONE_DAY}
          approverName={MARCUS.name}
          thisYear={THIS_YEAR}
          onSubmit={close}
          onClose={close}
        />
      )}
    </>
  )
}

export function TimeOffSections() {
  return (
    <>
      <Group title="Time off: status badge">
        <Section id="status-badge-waiting" title="Status badge, waiting for approval">
          <StatusBadge status="waiting" />
        </Section>
        <Section id="status-badge-approved" title="Status badge, approved">
          <StatusBadge status="approved" />
        </Section>
        <Section id="status-badge-denied" title="Status badge, denied (ink, never red)">
          <StatusBadge status="denied" />
        </Section>
        <Section id="status-badge-recorded" title="Status badge, recorded">
          <StatusBadge status="recorded" />
        </Section>
        <Section id="status-badge-canceled" title="Status badge, canceled">
          <StatusBadge status="canceled" />
        </Section>
      </Group>
      <Group title="Time off: segmented control and choice group">
        <Section id="segmented-control-default" title="Segmented control, default (PTO)">
          <Type initial="pto" />
        </Section>
        <Section id="segmented-control-selected" title="Segmented control, Sick time selected">
          <Type initial="sick" />
        </Section>
        <Section id="segmented-control-disabled" title="Segmented control, disabled">
          <Type initial="pto" disabled />
        </Section>
        <Section id="choice-group-default" title="Choice group, default (Full day)">
          <Choice initial="full" />
        </Section>
        <Section id="choice-group-selected" title="Choice group, Half day selected">
          <Choice initial="half" />
        </Section>
        <Section id="choice-group-disabled" title="Choice group, disabled">
          <Choice initial="full" disabled />
        </Section>
      </Group>
      <Group title="Time off: hours stepper">
        <Section id="hours-stepper-default" title="Hours stepper, default">
          <Stepper initial="3" />
        </Section>
        <Section id="hours-stepper-at-1" title="Hours stepper, at 1 (Fewer hours is off)">
          <Stepper initial="1" />
        </Section>
        <Section id="hours-stepper-at-8" title="Hours stepper, at 8 (More hours is off)">
          <Stepper initial="8" />
        </Section>
        <Section id="hours-stepper-error" title="Hours stepper, error">
          <Stepper initial="12" />
        </Section>
        <Section id="hours-stepper-disabled" title="Hours stepper, disabled">
          <Stepper initial="3" disabled />
        </Section>
      </Group>
      <Group title="Time off: dates field">
        <Section id="date-field-empty" title="Dates field, empty">
          <Field />
        </Section>
        <Section id="date-field-one-day" title="Dates field, one day">
          <Field start="2026-10-30" />
        </Section>
        <Section id="date-field-range" title="Dates field, a range">
          <Field start="2026-11-25" end="2026-11-27" />
        </Section>
        <Section id="date-field-open" title="Dates field, open">
          <Field start="2026-11-25" end="2026-11-27" open />
        </Section>
        <Section id="date-field-error" title="Dates field, error">
          <Field error="Pick at least one day." />
        </Section>
        <Section id="date-field-disabled" title="Dates field, disabled">
          <Field start="2026-11-25" end="2026-11-27" disabled />
        </Section>
      </Group>
      <Group title="Time off: date picker">
        <Section id="date-picker-pto" title="Date picker, PTO (past days struck through)">
          <Picker id="gallery-picker-pto" minDate={TODAY} pastLabel={timeOffCopy.pastLabelPto} />
        </Section>
        <Section id="date-picker-sick" title="Date picker, sick time (the last 30 days open)">
          <Picker
            id="gallery-picker-sick"
            minDate={SICK_EARLIEST}
            pastLabel={pastLabelSick(30, SICK_EARLIEST)}
          />
        </Section>
        <Section id="date-picker-range" title="Date picker, November 25 to 27 chosen">
          <Picker
            id="gallery-picker-range"
            minDate={TODAY}
            pastLabel={timeOffCopy.pastLabelPto}
            initial={{ start: '2026-11-25', end: '2026-11-27' }}
          />
        </Section>
      </Group>
      <Group title="Time off: form messages">
        <Section id="form-message-warning" title="Form message, warning (never blocks)">
          <div className="w-[372px] max-w-full">
            <FormMessage tone="warning">
              More than 3 days usually needs 2 weeks’ notice. You can still request it.
            </FormMessage>
          </div>
        </Section>
        <Section id="form-message-refusal" title="Form message, refusal">
          <div className="w-[372px] max-w-full">
            <FormMessage tone="refusal">
              You have 92 hours (11.5 days) available. This request needs 120 hours (15 days).
            </FormMessage>
          </div>
        </Section>
      </Group>
      <Group title="Time off: alert dialog">
        <Section
          id="alert-dialog-cancel-request"
          title="Alert dialog, cancel a request: press the button"
        >
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="secondary">Cancel time off</Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogTitle>Cancel your time off on Wednesday, December 23?</AlertDialogTitle>
              <AlertDialogDescription>8 hours go back to your balance.</AlertDialogDescription>
              <AlertDialogActions>
                <AlertDialogCancel>Keep it</AlertDialogCancel>
                <AlertDialogConfirm>Cancel request</AlertDialogConfirm>
              </AlertDialogActions>
            </AlertDialogContent>
          </AlertDialog>
        </Section>
      </Group>
      <Group title="Time off: balance cards">
        <Section id="balance-card-pto" title="Balance card, PTO">
          <div className="w-[360px] max-w-full">
            <BalanceCard kind="pto" balance={PTO_BALANCE} rule={PTO_RULE} />
          </div>
        </Section>
        <Section id="balance-card-ceiling" title="Balance card, PTO at the limit (earning paused)">
          <div className="w-[360px] max-w-full">
            <BalanceCard kind="pto" balance={PTO_BALANCE_CEILING} rule={PTO_RULE} />
          </div>
        </Section>
        <Section id="balance-card-sick" title="Balance card, sick leave">
          <div className="w-[360px] max-w-full">
            <BalanceCard kind="sick" year={SICK_YEAR} rule={SICK_RULE} />
          </div>
        </Section>
        <Section id="balance-card-empty" title="Balance card, PTO with no requests">
          <div className="flex w-full min-w-0 flex-wrap gap-4">
            <div className="w-[360px] max-w-full">
              <BalanceCard kind="pto" balance={PTO_BALANCE_EMPTY} rule={PTO_RULE} />
            </div>
            <div className="w-[360px] max-w-full">
              <BalanceCard kind="sick" year={SICK_YEAR_EMPTY} rule={SICK_RULE} />
            </div>
          </div>
        </Section>
        <Section id="balance-card-loading" title="Balance card, loading">
          <div className="w-[360px] max-w-full">
            <BalanceCard kind="loading" />
          </div>
        </Section>
      </Group>
      <Group title="Time off: request rows">
        <Section id="request-row-approved" title="Request row, approved, with Cancel">
          <Rows>
            <RequestRow variant="mine" request={MINE_APPROVED} canCancel onCancel={() => {}} />
          </Rows>
        </Section>
        <Section id="request-row-waiting" title="Request row, waiting for approval, with Cancel">
          <Rows>
            <RequestRow variant="mine" request={MINE_WAITING} canCancel onCancel={() => {}} />
          </Rows>
        </Section>
        <Section id="request-row-recorded" title="Request row, sick time recorded">
          <Rows>
            <RequestRow variant="mine" request={MINE_RECORDED} />
          </Rows>
        </Section>
        <Section id="request-row-canceled" title="Request row, canceled">
          <Rows>
            <RequestRow variant="mine" request={MINE_CANCELED} />
          </Rows>
        </Section>
        <Section id="request-row-denied" title="Request row, denied, with the manager’s note">
          <Rows>
            <RequestRow variant="mine" request={MINE_DENIED} />
          </Rows>
        </Section>
        <Section id="request-row-team" title="Request row, a team member’s, approved">
          <Rows>
            <RequestRow
              variant="team"
              request={TEAM_APPROVED}
              decidedLine={decisionLine('approved', TEAM_APPROVED.decidedAt, TODAY, TIME_ZONE)}
            />
          </Rows>
        </Section>
        <Section
          id="request-row-team-denied"
          title="Request row, a team member’s, denied with a note"
        >
          <Rows>
            <RequestRow
              variant="team"
              request={TEAM_DENIED}
              decidedLine={decisionLine('denied', TEAM_DENIED.decidedAt, TODAY, TIME_ZONE)}
              noteLabel="Your note"
            />
          </Rows>
        </Section>
        <Section id="request-group-upcoming" title="Request group, Upcoming and Past">
          <GroupFrame>
            <RequestGroup title="Upcoming" empty="No upcoming time off.">
              <RequestRow variant="mine" request={MINE_WAITING} canCancel onCancel={() => {}} />
              <RequestRow variant="mine" request={MINE_APPROVED} canCancel onCancel={() => {}} />
            </RequestGroup>
            <RequestGroup title="Past" empty="No past time off.">
              <RequestRow variant="mine" request={MINE_CANCELED} />
              <RequestRow variant="mine" request={MINE_DENIED} />
            </RequestGroup>
          </GroupFrame>
        </Section>
        <Section id="request-group-empty" title="Request group, empty">
          <GroupFrame>
            <RequestGroup title="Upcoming" empty="No upcoming time off." />
          </GroupFrame>
        </Section>
      </Group>
      <Group title="Time off: what this uses">
        <Section id="preview-block-one-day" title="Preview, one day">
          <Preview check={CHECK_ONE_DAY} />
        </Section>
        <Section id="preview-block-weekend" title="Preview, weekend skipped">
          <Preview check={CHECK_WEEKEND} />
        </Section>
        <Section id="preview-block-holiday" title="Preview, holiday skipped">
          <Preview check={CHECK_HOLIDAY} />
        </Section>
        <Section id="preview-block-sick-hours" title="Preview, sick time in hours">
          <Preview check={CHECK_SICK_HOURS} type="sick" />
        </Section>
        <Section id="preview-block-already-booked" title="Preview, a day already booked">
          <Preview check={CHECK_OVERLAP} refused />
        </Section>
        <Section id="preview-block-runs" title="Preview, more than five days in runs">
          <Preview check={CHECK_LONG_RUNS} />
        </Section>
        <Section id="preview-block-cross-year-sick" title="Preview, sick time across New Year">
          <Preview check={CHECK_CROSS_YEAR_SICK} type="sick" />
        </Section>
        <Section id="preview-block-nothing-picked" title="Preview, nothing picked">
          <div className="w-[372px] max-w-full">
            <PreviewBlock
              type="pto"
              countedDays={[]}
              skippedDays={[]}
              amountLabel={null}
              draws={[]}
              rules={[]}
              empty
            />
          </div>
        </Section>
        <Section id="preview-block-nothing-counted" title="Preview, no day counts">
          <Preview check={CHECK_NOTHING_COUNTED} refused />
        </Section>
      </Group>
      <Group title="Time off: request form">
        <Section id="request-form-pto-one-day" title="Request form, PTO, one day">
          <FormFrame start="2026-10-30" check={CHECK_ONE_DAY} />
        </Section>
        <Section id="request-form-holiday-range" title="Request form, PTO over a holiday">
          <FormFrame start="2026-11-25" end="2026-11-27" check={CHECK_HOLIDAY} />
        </Section>
        <Section id="request-form-sick-hours" title="Request form, sick time in hours">
          <FormFrame
            type="sick"
            start="2026-10-22"
            howMuch="hours"
            hours="3"
            check={CHECK_SICK_HOURS}
          />
        </Section>
        <Section id="request-form-short-notice" title="Request form, short notice (warning)">
          <FormFrame start="2026-11-02" end="2026-11-05" check={CHECK_SHORT_NOTICE} />
        </Section>
        <Section id="request-form-not-enough" title="Request form, not enough PTO (refusal)">
          <FormFrame start="2026-11-30" end="2026-12-18" check={CHECK_NOT_ENOUGH} />
        </Section>
        <Section id="request-form-overlap" title="Request form, already booked (refusal)">
          <FormFrame start="2026-12-23" check={CHECK_OVERLAP} />
        </Section>
        <Section id="request-form-submitting" title="Request form, submitting">
          <FormFrame start="2026-10-30" check={CHECK_ONE_DAY} submitting />
        </Section>
        <Section
          id="request-form-sheet"
          title="Request form, the phone's bottom sheet: press the button"
        >
          <SheetDemo />
        </Section>
      </Group>
    </>
  )
}
