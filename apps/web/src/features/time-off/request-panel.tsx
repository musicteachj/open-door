import { useEffect, useRef, useState } from 'react'
import type { CalendarOut, CheckOut, RequestOut } from '@/api/generated'
import {
  resolveChoice,
  type HowMuch,
  type LeaveKind,
  type SubmitChoice,
} from '@/components/timeoff/choice'
import type { DatePickerSelection } from '@/components/timeoff/date-picker'
import { pageCopy, pastLabelSick, timeOffCopy } from '@/components/timeoff/labels'
import { RequestForm } from '@/components/timeoff/request-form'
import { ApiError } from '@/lib/api-fetch'
import { toPossibleRequest } from './request-input'
import { useCheckTimeOff, useCreateTimeOff } from './use-time-off'

type RequestPanelProps = {
  /** A docked, non-modal panel beside the page (a wide window) or a modal bottom sheet. */
  docked: boolean
  /** The id the "Request time off" button's `aria-controls` points at. */
  id?: string
  /** Today at the person's location, from the API. */
  today: string
  calendar: CalendarOut
  /** The manager named in the form's footer. */
  approverName?: string | null
  /** Close and Cancel. The page puts focus back on "Request time off". */
  onClose: () => void
  /** The request was made. The page closes the form, says so, and puts focus back. */
  onSubmitted: (request: RequestOut) => void
}

/** The last answer the server gave, and the inputs it was for (null when it could not say). */
type Settled = { key: string | null; answer: CheckOut | null }

/**
 * The request form with its state (Task 35): the page mounts it while the form is open, so closing
 * throws away the inputs and opening starts clean. It owns the type, the dates, how much, and the
 * hours, asks `POST /time-off/check` on each change, and sends `POST /time-off/requests` with what
 * the form reports.
 *
 * `checking` is true from the render in which an input changes until the answer for those inputs
 * arrives (it is worked out from the answer's own key, so there is no render in between), and an
 * answer that arrives for older inputs is dropped. Until the new answer lands the old one shows
 * muted and Submit waits.
 */
function RequestPanel({
  docked,
  id,
  today,
  calendar,
  approverName,
  onClose,
  onSubmitted,
}: RequestPanelProps) {
  const [type, setType] = useState<LeaveKind>('pto')
  const [selection, setSelection] = useState<DatePickerSelection>()
  const [howMuch, setHowMuch] = useState<HowMuch>('full')
  const [hours, setHours] = useState('3')
  const [settled, setSettled] = useState<Settled>({ key: null, answer: null })
  // Bumped to ask again for inputs that haven't changed (after the server refused a send).
  const [round, setRound] = useState(0)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const { mutateAsync: askCheck } = useCheckTimeOff()
  const create = useCreateTimeOff()
  // One send at a time. A ref, not the mutation's `isPending`, which two quick presses both read
  // as false before the page draws again.
  const sending = useRef(false)

  const start = selection?.start
  const end = selection?.end
  const choice = resolveChoice(type, start, end, howMuch, hours)
  const body = toPossibleRequest(type, start, end, choice, calendar.halfDayMinutes)
  const key = body === null ? null : JSON.stringify(body)

  // The check for the current inputs. The effect's cleanup marks its answer as stale, so one that
  // lands after the inputs changed again (or the form closed) is dropped.
  useEffect(() => {
    if (key === null) return
    let current = true
    const asked = JSON.parse(key) as NonNullable<typeof body>
    askCheck({ data: asked })
      .then((answer) => {
        if (current) setSettled({ key, answer })
      })
      .catch(() => {
        if (current) setSettled({ key, answer: null })
      })
    return () => {
      current = false
    }
    // Only a change of inputs, or a round, asks again.
  }, [key, round, askCheck])

  // With nothing to ask there is nothing to show, and nothing is on its way.
  const answer = key === null ? null : settled.answer
  const checking = key !== null && settled.key !== key
  const sick = type === 'sick'
  const minDate = sick ? calendar.earliestStart.sick : calendar.earliestStart.pto

  function changed<T>(set: (value: T) => void) {
    return (value: T) => {
      setSubmitError(null)
      set(value)
    }
  }

  async function submit(sent: SubmitChoice) {
    const request = toPossibleRequest(type, start, end, sent, calendar.halfDayMinutes)
    if (request === null || sending.current) return
    sending.current = true
    setSubmitError(null)
    try {
      onSubmitted(await create.mutateAsync({ data: request }))
    } catch (error) {
      if (error instanceof ApiError && error.problem?.detail) {
        setSubmitError(error.problem.detail)
        // The server may now say something different from the preview, so read it again.
        setSettled({ key: null, answer: settled.answer })
        setRound((round) => round + 1)
      } else {
        setSubmitError(pageCopy.submitFailed)
      }
    } finally {
      sending.current = false
    }
  }

  return (
    <RequestForm
      docked={docked}
      id={id}
      type={type}
      onTypeChange={changed(setType)}
      start={start}
      end={end}
      onDatesChange={changed(setSelection)}
      calendar={{
        today,
        minDate,
        maxDate: calendar.latestEnd,
        scheduledWeekdays: calendar.scheduledWeekdays,
        holidays: calendar.holidays,
        pastLabel: sick
          ? pastLabelSick(calendar.sickLookbackDays, minDate)
          : timeOffCopy.pastLabelPto,
      }}
      howMuch={howMuch}
      onHowMuchChange={changed(setHowMuch)}
      hours={hours}
      onHoursChange={changed(setHours)}
      check={answer}
      approverName={approverName}
      thisYear={Number(today.slice(0, 4))}
      checking={checking}
      previewFailed={key !== null && !checking && answer === null}
      onRetryPreview={() => {
        // The same inputs again: no answer is held for them, so the preview shows as checking.
        setSettled({ key: null, answer: null })
        setRound((round) => round + 1)
      }}
      submitting={create.isPending}
      submitError={submitError}
      onSubmit={(sent) => void submit(sent)}
      onClose={onClose}
    />
  )
}

export { RequestPanel }
export type { RequestPanelProps }
