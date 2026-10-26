import {
  Ban,
  CalendarPlus,
  CalendarX,
  CircleAlert,
  CircleCheck,
  ClipboardCheck,
  Clock,
  Info,
  RotateCcw,
  type LucideIcon,
} from 'lucide-react'
import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { Link } from 'react-router'
import type { CanceledReason, Card, FailureOut, ProposalStatus } from '@/api/generated'
import { CoverageLine } from '@/components/approvals/coverage-line'
import { NoteField } from '@/components/approvals/note-field'
import { firstNameOf } from '@/components/approvals/labels'
import { FormMessage } from '@/components/timeoff/form-message'
import { PreviewBlock } from '@/components/timeoff/preview-block'
import { RuleChips } from '@/components/timeoff/rule-chip'
import { StatusBadge } from '@/components/timeoff/status-badge'
import { longRange } from '@/components/timeoff/dates'
import {
  availableAfter,
  availableNow,
  failureText,
  formCopy,
  typeLabel,
} from '@/components/timeoff/labels'
import { trimLikePython } from './text-count'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { initialsOf } from '@/lib/initials'
import { cn } from '@/lib/utils'
import {
  cardTitle,
  confirmCopy,
  confirmLabel,
  confirmName,
  dismissName,
  endedText,
  executedBadge,
  executedText,
  expiryLabel,
  failureVerb,
} from './confirm-labels'

type ConfirmCardProps = {
  /** The card the server built from the engine's figures. Every figure on it is an API label. */
  card: Card
  status: ProposalStatus
  canceledReason?: CanceledReason | null
  failure?: FailureOut | null
  expiresAt: string
  /** The zone the expiry time is written in. */
  timeZone: string
  /** The proposal's turn is still streaming: Confirm waits, Dismiss works. */
  turnRunning?: boolean
  /** Confirm was pressed and the server is working. */
  confirming?: boolean
  /** A denial's note, owned by the page while the card is pending. */
  note?: string
  onNoteChange?: (note: string) => void
  /** The note a denial carried, for the executed card's "Your note" box. */
  deniedNote?: string | null
  /** The current year, so sick time in another year names its year. */
  thisYear?: number
  timeOffHref?: string
  approvalsHref?: string
  onConfirm?: () => void
  onDismiss?: () => void
  onAskAgain?: () => void
  className?: string
}

const ICONS: Record<'request' | 'sick' | 'decide' | 'cancel', LucideIcon> = {
  request: CalendarPlus,
  sick: CalendarPlus,
  decide: ClipboardCheck,
  cancel: CalendarX,
}

const dateText = (card: Card) => longRange(card.startDate, card.endDate)

type FactRow = { label: string; value: ReactNode; strong?: boolean }

function factRows(card: Card, executed: boolean): FactRow[] {
  const rows: FactRow[] = [
    { label: confirmCopy.factType, value: typeLabel(card.type) },
    { label: confirmCopy.factDates, value: dateText(card), strong: true },
  ]
  if (card.kind === 'decide') {
    rows.push({ label: confirmCopy.factAmount, value: card.amountLabel })
    if (card.availableAfterLabel) {
      rows.push({
        label: confirmCopy.factBalance,
        // A denial gives the hours back, and the figure already counts the waiting request, so
        // it is what is available now. An approval changes nothing, so it is after this.
        value:
          card.decision === 'deny'
            ? availableNow(card.availableAfterLabel)
            : availableAfter(card.availableAfterLabel),
      })
    }
  }
  if (card.kind === 'cancel') {
    rows.push({
      label: confirmCopy.factAmount,
      value:
        card.returnsLabel && card.returnsMinutes
          ? confirmCopy.amountGoBack(card.returnsLabel)
          : card.amountLabel,
    })
    if (card.availableAfterLabel) {
      rows.push({
        label: confirmCopy.factBalance,
        value: availableAfter(card.availableAfterLabel),
      })
    }
    // The old status would contradict the Canceled badge once the card is a record.
    if (!executed) {
      rows.push({ label: confirmCopy.factStatus, value: <StatusBadge status={card.status} /> })
    }
  }
  return rows
}

/**
 * A proposed time-off action in the conversation (ConfirmCard.jsx). The assistant never acts: the
 * card names the action, lists the facts from the engine, and waits for a person. One component
 * for the five variants and every state: pending (with Confirm and Dismiss), still streaming,
 * confirming, executed, failed, dismissed or replaced, and expired. It calls no API: the page
 * wires the callbacks.
 *
 * After a final state the buttons never come back. When the card moves on from pending while focus
 * is inside it, or was on a button that went away, focus moves to the outcome line (or to "Ask
 * again" for an expired card). Focus anywhere else on the page is left alone.
 */
function ConfirmCard({
  card,
  status,
  canceledReason = null,
  failure = null,
  expiresAt,
  timeZone,
  turnRunning = false,
  confirming = false,
  note = '',
  onNoteChange,
  deniedNote = null,
  thisYear,
  timeOffHref = '/time-off',
  approvalsHref = '/approvals',
  onConfirm,
  onDismiss,
  onAskAgain,
  className,
}: ConfirmCardProps) {
  const titleId = useId()
  const waitId = useId()
  const rootRef = useRef<HTMLElement>(null)
  const outcomeRef = useRef<HTMLElement | null>(null)
  const setOutcome = useCallback((node: HTMLElement | null) => {
    outcomeRef.current = node
  }, [])
  const askAgainRef = useRef<HTMLButtonElement>(null)
  const previousStatus = useRef(status)
  // A button on this card was pressed: the card's own change of state may take focus.
  const touched = useRef(false)
  // Whether focus was inside the card when this render began, before a button could be removed
  // from the page (a removed button leaves focus on the body).
  const focusWasInside = useRef(false)
  // This reads the page's focus on purpose: it is the one moment before a status change can remove
  // the focused button, and nothing rendered depends on it.
  // oxlint-disable-next-line react/refs
  focusWasInside.current = Boolean(rootRef.current?.contains(document.activeElement))

  useLayoutEffect(() => {
    const before = previousStatus.current
    previousStatus.current = status
    if (before !== 'pending' || status === 'pending') return
    const inside =
      focusWasInside.current || Boolean(rootRef.current?.contains(document.activeElement))
    const pressed = touched.current
    touched.current = false
    // A card changed by the server or the clock (replaced, expired) never takes focus from
    // somewhere else, or from nowhere: only a card the person was using does.
    if (status === 'expired') {
      if (inside) askAgainRef.current?.focus()
    } else if (inside || pressed) {
      outcomeRef.current?.focus()
    }
  }, [status])

  // A press only counts while it can still end the card. Once the work stops without a new status
  // (a failed send, a refusal the page handles), or focus goes to something outside the card, the
  // press is forgotten, so a later change from the server never takes focus from where it is.
  const wasConfirming = useRef(false)
  useEffect(() => {
    if (wasConfirming.current && !confirming && status === 'pending') touched.current = false
    wasConfirming.current = confirming
  }, [confirming, status])

  useEffect(() => {
    if (status !== 'pending') return
    const onFocusIn = (event: FocusEvent) => {
      if (event.target instanceof Node && !rootRef.current?.contains(event.target)) {
        touched.current = false
      }
    }
    document.addEventListener('focusin', onFocusIn)
    return () => document.removeEventListener('focusin', onFocusIn)
  }, [status])

  // A failure is announced when the card turns failed while on the page, not when a card that is
  // already failed is first drawn (a conversation opened again).
  const [announceFailure] = useState(status !== 'failed')
  const pending = status === 'pending'
  const executed = status === 'executed'
  const failed = status === 'failed'
  const muted = failed || status === 'canceled' || status === 'expired'
  const kind = card.kind === 'request' && card.type === 'sick' ? 'sick' : card.kind
  const Icon = ICONS[kind]
  const denial = card.kind === 'decide' && card.decision === 'deny'
  const requesterFirst = card.kind === 'decide' ? firstNameOf(card.requester.name) : ''
  // The server decides whether a denial had a note with Python's strip, so this does too.
  const hasNote = trimLikePython(deniedNote ?? '') !== ''
  const ink = muted ? 'text-ink-muted' : undefined
  const infoLine =
    card.kind !== 'request'
      ? ''
      : card.type === 'sick'
        ? confirmCopy.sickInfo
        : card.approver
          ? formCopy.approverNote(card.approver.name)
          : ''

  return (
    <section
      ref={rootRef}
      data-slot="confirm-card"
      data-state={status}
      data-muted={muted ? '' : undefined}
      aria-labelledby={titleId}
      className={cn(
        'overflow-hidden rounded-lg border border-border bg-surface-raised text-ink',
        className,
      )}
    >
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle px-5 py-3.5 max-sm:px-4">
        <div className="flex min-w-0 items-center gap-3">
          <span
            data-slot="confirm-card-tile"
            aria-hidden="true"
            className={cn(
              'flex size-8 flex-none items-center justify-center rounded-sm',
              muted ? 'bg-surface-hover text-ink-muted' : 'bg-primary-tint text-primary',
            )}
          >
            <Icon className="size-[18px]" />
          </span>
          <h3 id={titleId} className={cn('m-0 text-body font-semibold', ink)}>
            {cardTitle(card)}
          </h3>
        </div>
        {pending && (
          <span className="inline-flex items-center gap-1.5 text-small whitespace-nowrap text-ink-muted tabular-nums">
            <Clock aria-hidden="true" className="size-3.5" />
            {confirmCopy.expires(expiryLabel(expiresAt, timeZone))}
          </span>
        )}
        {executed && <StatusBadge status={executedBadge(card)} />}
      </header>

      <div className="flex flex-col gap-4 px-5 pt-4 pb-5 max-sm:px-4">
        {card.kind === 'decide' && (
          <div className="flex items-center gap-3">
            <Avatar size="lg" muted={muted} aria-hidden="true">
              <AvatarFallback>{initialsOf(card.requester.name)}</AvatarFallback>
            </Avatar>
            <div className="flex flex-col">
              <span className={cn('text-body font-semibold', ink)}>{card.requester.name}</span>
              <span className="text-small text-ink-muted">{card.requester.title}</span>
            </div>
          </div>
        )}
        <dl className="m-0 grid grid-cols-[96px_minmax(0,1fr)] items-center gap-x-4 gap-y-2 text-ui max-sm:grid-cols-[minmax(0,1fr)] max-sm:gap-y-0.5">
          {factRows(card, executed).map((row) => (
            <FactItem key={row.label} row={row} muted={muted} />
          ))}
        </dl>
        {card.kind === 'request' && (
          <PreviewBlock
            type={card.type}
            countedDays={card.countedDays}
            skippedDays={card.skippedDays}
            amountLabel={card.amountLabel}
            draws={card.draws}
            rules={card.rules}
            thisYear={thisYear}
            muted={muted}
          />
        )}
        {card.kind === 'decide' && (
          <CoverageLine
            coverage={card.coverage}
            multiDay={card.startDate !== card.endDate}
            muted={muted}
          />
        )}
        {infoLine && (
          <p className="m-0 flex items-start gap-2 text-ui text-pretty text-ink-muted">
            <Info aria-hidden="true" className="mt-0.5 size-4 flex-none" />
            {infoLine}
          </p>
        )}
        {card.kind === 'request' && pending && card.warnings.includes('short-notice') && (
          <FormMessage tone="warning">{formCopy.shortNotice}</FormMessage>
        )}
        {denial && pending && (
          <NoteField
            firstName={requesterFirst}
            value={note}
            onChange={onNoteChange ?? (() => {})}
            disabled={confirming || turnRunning}
          />
        )}
        {denial && executed && hasNote && (
          <div className="flex flex-col gap-0.5 rounded-md border border-border-subtle bg-surface-sunken px-3.5 py-2.5">
            <span className="text-small text-ink-muted">{confirmCopy.yourNote}</span>
            <p className="m-0 text-ui/5.5 text-pretty">“{trimLikePython(deniedNote ?? '')}”</p>
          </div>
        )}
        {card.kind !== 'request' && <RuleChips rules={card.rules} />}
      </div>

      {pending && (
        <div
          data-slot="confirm-card-footer"
          className="flex flex-col gap-3 border-t border-border-subtle bg-surface-sunken px-5 pt-3.5 pb-4 max-sm:px-4"
        >
          <p className="m-0 flex items-center gap-2 text-ui">
            {/* The AI tag is 11/16 semibold, as in the assistant message; no type token matches it. */}
            <span
              aria-hidden="true"
              className="inline-flex h-5 items-center rounded-xs border border-border-strong bg-surface-raised px-1.5 text-[11px]/4 font-semibold tracking-[0.03em]"
            >
              AI
            </span>
            {confirmCopy.proposed}
          </p>
          <div className="flex flex-wrap items-center gap-3 max-sm:grid max-sm:grid-cols-2">
            <Button
              loading={confirming}
              aria-label={confirming ? undefined : confirmName(card)}
              aria-disabled={turnRunning || undefined}
              aria-describedby={turnRunning ? waitId : undefined}
              onClick={
                turnRunning
                  ? undefined
                  : () => {
                      touched.current = true
                      onConfirm?.()
                    }
              }
              className="aria-disabled:cursor-not-allowed aria-disabled:bg-disabled-bg aria-disabled:text-disabled-fg aria-disabled:hover:bg-disabled-bg! max-sm:justify-center"
            >
              {confirming ? confirmCopy.confirming : confirmLabel(card)}
            </Button>
            <Button
              variant="secondary"
              disabled={confirming}
              aria-label={dismissName(card)}
              onClick={() => {
                touched.current = true
                onDismiss?.()
              }}
              className="max-sm:justify-center"
            >
              {confirmCopy.dismiss}
            </Button>
            {turnRunning && (
              <span id={waitId} className="text-small text-ink-muted max-sm:col-span-full">
                {confirmCopy.wait}
              </span>
            )}
          </div>
        </div>
      )}

      {executed && (
        <output
          ref={setOutcome}
          tabIndex={-1}
          className="flex flex-wrap items-center gap-2.5 border-t border-apricot-border bg-apricot-tint px-5 py-3.5 outline-none motion-safe:animate-confirm-in max-sm:px-4"
        >
          <CircleCheck aria-hidden="true" className="size-[18px] flex-none text-success" />
          <p className="m-0 min-w-50 flex-1 text-ui text-pretty">
            {executedText(card, { withNote: hasNote })}
          </p>
          <Link
            to={card.kind === 'decide' ? approvalsHref : timeOffHref}
            className="text-ui font-semibold whitespace-nowrap text-primary underline decoration-1 underline-offset-[3px]"
          >
            {card.kind === 'decide' ? confirmCopy.viewApprovals : confirmCopy.viewTimeOff}
          </Link>
        </output>
      )}

      {failed && (
        <div
          ref={setOutcome}
          data-slot="confirm-card-outcome"
          role={announceFailure ? 'alert' : undefined}
          tabIndex={-1}
          className="flex items-start gap-2.5 border-t border-danger-border bg-danger-tint px-5 py-3.5 outline-none max-sm:px-4"
        >
          <CircleAlert aria-hidden="true" className="mt-px size-[18px] flex-none text-danger" />
          <p className="m-0 min-w-50 flex-1 text-ui text-pretty">
            {failureText(
              failure ?? { code: 'unknown', text: confirmCopy.unknownFailure },
              failureVerb(card),
            )}
          </p>
        </div>
      )}

      {(status === 'canceled' || status === 'expired') && (
        <output
          ref={setOutcome}
          tabIndex={-1}
          className="flex flex-wrap items-center gap-2.5 border-t border-border-subtle bg-surface-sunken px-5 py-3 outline-none max-sm:px-4"
        >
          <Ban aria-hidden="true" className="size-[18px] flex-none text-ink-muted" />
          <p className="m-0 min-w-50 flex-1 text-ui text-pretty">
            {endedText(status, canceledReason)}
          </p>
          {status === 'expired' && (
            <Button
              ref={askAgainRef}
              variant="secondary"
              size="sm"
              onClick={() => {
                touched.current = true
                onAskAgain?.()
              }}
            >
              <RotateCcw aria-hidden="true" className="size-3.5" />
              {confirmCopy.askAgain}
            </Button>
          )}
        </output>
      )}
    </section>
  )
}

function FactItem({ row, muted }: { row: FactRow; muted: boolean }) {
  return (
    <>
      <dt className="text-ink-muted">{row.label}</dt>
      <dd
        className={cn(
          'm-0 flex text-pretty tabular-nums max-sm:mb-2',
          row.strong && 'font-semibold',
          muted && 'text-ink-muted',
        )}
      >
        {row.value}
      </dd>
    </>
  )
}

export { ConfirmCard }
export type { ConfirmCardProps }
