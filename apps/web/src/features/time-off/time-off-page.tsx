import { Clock } from 'lucide-react'
import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import type { RequestOut } from '@/api/generated'
import { useMe } from '@/app/useMe'
import { PageHeader } from '@/components/core/page-header'
import { LoadingStatus } from '@/components/feedback/loading-status'
import { BalanceCard } from '@/components/timeoff/balance-card'
import { addDays, endOfNextYear } from '@/components/timeoff/dates'
import {
  canceledToast,
  pageCopy,
  scheduleLine,
  sickCardLabel,
  submittedToast,
} from '@/components/timeoff/labels'
import { RequestGroup } from '@/components/timeoff/request-group'
import { RequestRow } from '@/components/timeoff/request-row'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { NARROW_WINDOW_QUERY } from '@/features/chat/conversation-source-panel'
import { PageSandboxIndicator } from '@/features/shell/page-sandbox-indicator'
import { useShellLayout } from '@/features/shell/shell-layout-store'
import { useShellToast } from '@/features/shell/toast-store'
import { useMediaQuery } from '@/hooks/use-media-query'
import { ApiError } from '@/lib/api-fetch'
import { cn } from '@/lib/utils'
import { CancelRequestDialog } from './cancel-request-dialog'
import { RequestPanel } from './request-panel'
import {
  useCancelTimeOff,
  useTimeOffBalances,
  useTimeOffCalendar,
  useTimeOffRequests,
  useTimeOffSummary,
} from './use-time-off'

// The Time off page at /time-off, from docs/design/screens/08-time-off: the balances, the schedule
// line with the button that opens the request form, and the person's requests. Every figure is the
// API's label. A failed first load goes to the route's error boundary (throwOnError).

/** How far back My requests reaches. It reaches ahead to the end of next year, the last day a request can name. */
const DAYS_BACK = 366

/** The id of the docked form, which "Request time off" controls. */
const FORM_ID = 'request-form'

/** Upcoming: open requests that haven't ended, soonest first. Past: everything else, newest first. */
function split(requests: RequestOut[], today: string) {
  const open = (request: RequestOut) =>
    (request.status === 'pending' ||
      request.status === 'approved' ||
      request.status === 'recorded') &&
    request.endDate >= today
  const upcoming = requests
    .filter(open)
    .sort(
      (a, b) => a.startDate.localeCompare(b.startDate) || a.createdAt.localeCompare(b.createdAt),
    )
  const past = requests
    .filter((request) => !open(request))
    .sort(
      (a, b) => b.startDate.localeCompare(a.startDate) || b.createdAt.localeCompare(a.createdAt),
    )
  return { upcoming, past }
}

function RequestsSkeleton() {
  return (
    <div aria-hidden="true" className="mt-6 flex flex-col gap-4" data-slot="requests-skeleton">
      {[0, 1, 2].map((row) => (
        <div key={row} className="flex flex-col gap-2 border-b border-border-subtle px-3 py-3.5">
          <Skeleton className="h-3.5 w-60 max-w-full" />
          <Skeleton className="h-2.5 w-40" />
        </div>
      ))}
    </div>
  )
}

export function TimeOffPage() {
  const { data: me } = useMe()
  // The docked form sticks in the window, so the shell's sheet clips instead of scrolling.
  const setStickyPanel = useShellLayout((s) => s.setStickyPanel)
  useLayoutEffect(() => {
    setStickyPanel(true)
    return () => setStickyPanel(false)
  }, [setStickyPanel])
  const balances = useTimeOffBalances(undefined, { throwOnError: true })
  const today = balances.data?.today
  const requests = useTimeOffRequests(
    {
      scope: 'mine',
      from: today ? addDays(today, -DAYS_BACK) : undefined,
      to: today ? endOfNextYear(today) : undefined,
    },
    { enabled: today !== undefined, throwOnError: true },
  )
  const calendar = useTimeOffCalendar(
    {
      // No `from`: the API starts at the earliest day sick time may start, so the look-back is
      // its number alone.
      to: today ? endOfNextYear(today) : '',
    },
    { enabled: today !== undefined, throwOnError: true },
  )
  // The approver is only a line in the form and the toast, so its failure isn't the page's.
  const summary = useTimeOffSummary()
  const cancel = useCancelTimeOff()

  const narrow = useMediaQuery(NARROW_WINDOW_QUERY)
  const docked = !narrow
  const [formOpen, setFormOpen] = useState(false)
  const [target, setTarget] = useState<RequestOut | null>(null)
  const requestButton = useRef<HTMLButtonElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const headingId = useId()
  // Where focus goes when the dialog closes: back to the row's Cancel (Keep it, Escape), or to the
  // heading once the row has moved (a cancel, or a request that turned out to be gone).
  const cancelOpener = useRef<HTMLElement | null>(null)
  const afterCancel = useRef<'opener' | 'heading'>('opener')
  // One cancel at a time. A ref, not the mutation's `isPending`, which two clicks before the page
  // draws again would both read as false.
  const canceling = useRef(false)
  // After the form closes, focus goes back to the button that opened it.
  const returnToButton = useRef(false)
  useEffect(() => {
    if (!formOpen && returnToButton.current) {
      returnToButton.current = false
      requestButton.current?.focus()
    }
  }, [formOpen])

  if (!me) return null
  const personId = me.id

  const loading = !balances.data || !requests.data || !calendar.data
  const { upcoming, past } =
    requests.data && today ? split(requests.data.items, today) : { upcoming: [], past: [] }

  function closeForm() {
    returnToButton.current = true
    setFormOpen(false)
  }

  function startCancel(request: RequestOut, button: HTMLButtonElement) {
    cancelOpener.current = button
    afterCancel.current = 'opener'
    setTarget(request)
  }

  // The toast belongs to the person who did it: `show` keys it to them, so a write that finishes
  // after a switch never reaches the new person.
  async function confirmCancel() {
    const request = target
    if (request === null || canceling.current) return
    canceling.current = true
    try {
      await cancel.mutateAsync({ requestId: request.id })
      useShellToast.getState().show(canceledToast(request.amountLabel), personId)
      afterCancel.current = 'heading'
    } catch (error) {
      // 409 (it changed, or already started) and 404 (gone) mean the row isn't what the page
      // showed, and the list has been read again, so the dialog closes. Anything else changed
      // nothing: a calm toast, and the dialog stays for another try.
      const changed = error instanceof ApiError && (error.status === 409 || error.status === 404)
      const said = error instanceof ApiError ? error.problem?.detail : null
      useShellToast
        .getState()
        .show(changed ? said || pageCopy.changedMeanwhile : pageCopy.cancelFailed, personId)
      canceling.current = false
      if (!changed) return
      afterCancel.current = 'heading'
      setTarget(null)
      return
    }
    canceling.current = false
    setTarget(null)
  }

  const sickRule = balances.data?.rules.find((rule) => rule.rule === 'sick-grant')
  const ptoRule = balances.data?.rules.find((rule) => rule.rule === 'pto-available')
  const thisYear = today ? Number(today.slice(0, 4)) : 0
  const dockedOpen = formOpen && docked

  return (
    <div className="flex min-h-0 flex-1">
      <div
        className={cn(
          'flex min-w-0 flex-1 flex-col px-14 pt-10 pb-12 max-[1100px]:px-12 max-[760px]:px-5 max-[760px]:pb-8',
          dockedOpen && 'px-10',
        )}
      >
        <div className="w-full max-w-232">
          <PageHeader title={pageCopy.title} right={<PageSandboxIndicator />} />
          <LoadingStatus loading={loading} text={pageCopy.loading} />

          <div className="mt-8 grid grid-cols-[repeat(auto-fit,minmax(300px,1fr))] gap-6">
            {balances.data ? (
              <>
                <BalanceCard kind="pto" balance={balances.data.pto} rule={ptoRule} />
                {balances.data.sick.map((year) => (
                  <BalanceCard
                    key={year.year}
                    kind="sick"
                    year={year}
                    rule={sickRule}
                    label={sickCardLabel(year.year, thisYear)}
                  />
                ))}
              </>
            ) : (
              <>
                <BalanceCard kind="loading" />
                <BalanceCard kind="loading" />
              </>
            )}
          </div>

          <div className="mt-6 flex flex-wrap items-center justify-between gap-x-6 gap-y-4">
            {calendar.data ? (
              <p className="m-0 flex items-start gap-2.5 text-ui text-ink">
                <Clock aria-hidden="true" className="mt-0.5 size-4 flex-none text-ink-muted" />
                {/* The dot trails the text before it (a no-break space keeps them together), and a
                    plain space comes before the link, so a wrapped line never starts with the dot. */}
                <span className="min-w-0">
                  <span>
                    {scheduleLine(calendar.data.scheduledWeekdays, calendar.data.dayLabel)}
                    {'\u00a0'}
                    <span className="mx-1">·</span>
                  </span>{' '}
                  <Link
                    to="/handbook/3.1"
                    className="font-medium text-primary underline underline-offset-3"
                  >
                    {pageCopy.scheduleSource}
                  </Link>
                </span>
              </p>
            ) : (
              <Skeleton className="h-3.5 w-80 max-w-full" />
            )}
            {!loading && (
              <Button
                ref={requestButton}
                aria-expanded={formOpen}
                aria-controls={dockedOpen ? FORM_ID : undefined}
                onClick={() => {
                  if (formOpen) closeForm()
                  else setFormOpen(true)
                }}
                className="max-sm:w-full"
              >
                {pageCopy.requestButton}
              </Button>
            )}
          </div>

          <section aria-labelledby={headingId} className="mt-10">
            <h2
              ref={heading}
              id={headingId}
              tabIndex={-1}
              className="m-0 text-h2 text-ink outline-none"
            >
              {pageCopy.myRequests}
            </h2>
            {loading ? (
              <RequestsSkeleton />
            ) : (
              <>
                <RequestGroup title={pageCopy.upcoming} empty={pageCopy.noUpcoming}>
                  {upcoming.map((request) => (
                    <RequestRow
                      key={request.id}
                      variant="mine"
                      request={request}
                      canCancel={request.canCancel}
                      onCancel={startCancel}
                    />
                  ))}
                </RequestGroup>
                <RequestGroup title={pageCopy.past} empty={pageCopy.noPast}>
                  {past.map((request) => (
                    <RequestRow
                      key={request.id}
                      variant="mine"
                      request={request}
                      canCancel={request.canCancel}
                      onCancel={startCancel}
                    />
                  ))}
                </RequestGroup>
              </>
            )}
          </section>
        </div>
      </div>

      {formOpen && calendar.data && today && (
        <PanelSlot docked={docked}>
          <RequestPanel
            docked={docked}
            id={FORM_ID}
            today={today}
            calendar={calendar.data}
            approverName={summary.data?.approver?.name}
            onClose={closeForm}
            onSubmitted={(request) => {
              useShellToast
                .getState()
                .show(submittedToast(request.type, summary.data?.approver?.name), personId)
              closeForm()
            }}
          />
        </PanelSlot>
      )}

      <CancelRequestDialog
        request={target}
        onOpenChange={(open) => {
          if (!open && !cancel.isPending) setTarget(null)
        }}
        canceling={cancel.isPending}
        onConfirm={() => void confirmCancel()}
        onCloseAutoFocus={(event) => {
          event.preventDefault()
          if (afterCancel.current === 'heading') heading.current?.focus()
          else cancelOpener.current?.focus()
        }}
      />
    </div>
  )
}

/**
 * Where the form sits. Docked, it is a column beside the page that stays in the window as the page
 * scrolls (the shell's sheet doesn't clip with a scroll container on this page, so `sticky` holds),
 * as tall as the window less the sheet's margins. As a bottom sheet it has no place in the page.
 */
function PanelSlot({ docked, children }: { docked: boolean; children: React.ReactNode }) {
  if (!docked) return children
  return <div className="sticky top-3 h-[calc(100dvh-24px)] flex-none self-start">{children}</div>
}
