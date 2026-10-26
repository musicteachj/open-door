import { useId, useRef, type ReactNode } from 'react'
import type { RequestOut } from '@/api/generated'
import { useMe } from '@/app/useMe'
import { ApprovalCard } from '@/components/approvals/approval-card'
import { DecisionDialog } from '@/components/approvals/decision-dialog'
import { approvalsPageCopy, decisionFacts } from '@/components/approvals/labels'
import { PageHeader } from '@/components/core/page-header'
import { LoadingStatus } from '@/components/feedback/loading-status'
import { addDays } from '@/components/timeoff/dates'
import { decisionLine } from '@/components/timeoff/labels'
import { RequestRow } from '@/components/timeoff/request-row'
import { Skeleton } from '@/components/ui/skeleton'
import { NotFound } from '@/features/global-states/pages'
import { PageSandboxIndicator } from '@/features/shell/page-sandbox-indicator'
import { useTimeOffRequests, useTimeOffSummary } from '@/features/time-off/use-time-off'
import { COMING_UP_DAYS, RECENT_DAYS, comingUp, waitingRequests } from './lists'
import { useDecisions, type Held } from './use-decisions'

// The Approvals page at /approvals, from docs/design/screens/09-approvals, for managers: the
// requests waiting for them with Approve and Deny, what is coming up on the team, and their own
// recent decisions. Every figure is the API's label. A failed first load goes to the route's error
// boundary (throwOnError). Only a manager sees it: anyone else gets the Not found page.

type Me = NonNullable<ReturnType<typeof useMe>['data']>

export function ApprovalsPage() {
  const { data: me } = useMe()
  if (!me) return null
  if (!me.isManager) return <NotFound />
  return <ManagerApprovals me={me} />
}

const subtitle = 'm-0 mt-1 text-ui text-ink-muted'

function SectionHeading({ id, children }: { id: string; children: ReactNode }) {
  return (
    <h2 id={id} className="m-0 text-h2 text-ink">
      {children}
    </h2>
  )
}

function Rows({ children }: { children: ReactNode }) {
  return <ul className="m-0 mt-4 list-none border-t border-border-subtle p-0">{children}</ul>
}

function RowsSkeleton() {
  return (
    <div aria-hidden="true" className="mt-4 flex flex-col border-t border-border-subtle">
      {[0, 1].map((row) => (
        <div key={row} className="flex flex-col gap-2 border-b border-border-subtle px-3 py-4">
          <Skeleton className="h-3.5 w-60 max-w-full" />
          <Skeleton className="h-2.5 w-40" />
        </div>
      ))}
    </div>
  )
}

function ManagerApprovals({ me }: { me: Me }) {
  // Today at the manager's location, from the summary (the nav and the rail read it too).
  const summary = useTimeOffSummary({ throwOnError: true })
  const today = summary.data?.today
  const waiting = useTimeOffRequests({ scope: 'waiting' }, { throwOnError: true })
  const upcoming = useTimeOffRequests(
    {
      scope: 'team',
      from: today,
      to: today ? addDays(today, COMING_UP_DAYS) : undefined,
    },
    { enabled: today !== undefined, throwOnError: true },
  )
  // The manager's own decisions, by the day each was made, however far ahead the leave is.
  const recent = useTimeOffRequests(
    {
      scope: 'decided',
      from: today ? addDays(today, -RECENT_DAYS) : undefined,
      to: today,
    },
    { enabled: today !== undefined, throwOnError: true },
  )
  const waitingId = useId()
  const comingUpId = useId()
  const recentId = useId()
  const heading = useRef<HTMLHeadingElement>(null)
  const list = useRef<HTMLUListElement>(null)

  // The cards on the page: what still waits, plus the cards held after a 409, each in the place
  // it was seen. `layout` is read when a decision ends, to find the next card and a held one's slot.
  const decisions = useDecisions({ personId: me.id, layout: () => layout })
  const heldIds = new Set(decisions.held.map((item) => item.request.id))
  const live = waitingRequests(waiting.data?.items ?? []).filter(
    (request) => !heldIds.has(request.id),
  )
  type Card = { request: RequestOut; held?: Held }
  const cards: Card[] = live.map((request) => ({ request }))
  for (const item of [...decisions.held].sort((a, b) => a.index - b.index)) {
    cards.splice(Math.min(item.index, cards.length), 0, { request: item.request, held: item })
  }
  const layout = {
    live: live.map((request) => request.id),
    order: cards.map((card) => card.request.id),
  }

  const loading =
    !summary.data || !waiting.data || !upcoming.data || !recent.data || today === undefined
  const timeZone = me.location.timezone
  const coming = today && upcoming.data ? comingUp(upcoming.data.items, today) : []
  const decided = recent.data?.items ?? []

  return (
    <div className="flex min-w-0 flex-col px-14 pt-10 pb-12 max-[1100px]:px-12 max-[760px]:px-5 max-[760px]:pb-8">
      <div className="w-full max-w-232">
        <PageHeader title={approvalsPageCopy.title} right={<PageSandboxIndicator />} />
        <LoadingStatus loading={loading} text={approvalsPageCopy.loading} />

        {loading ? (
          <div className="mt-8" data-slot="approvals-skeleton">
            <ul aria-hidden="true" className="m-0 flex list-none flex-col gap-4 p-0">
              <ApprovalCard loading />
              <ApprovalCard loading />
            </ul>
            <RowsSkeleton />
            <RowsSkeleton />
          </div>
        ) : (
          <>
            <section aria-labelledby={waitingId} className="mt-8">
              <h2
                ref={heading}
                id={waitingId}
                tabIndex={-1}
                aria-label={approvalsPageCopy.waitingName(live.length)}
                className="m-0 flex items-center gap-3 text-h2 text-ink outline-none"
              >
                {approvalsPageCopy.waiting}
                {live.length > 0 && (
                  <span
                    aria-hidden="true"
                    className="inline-flex h-6 min-w-6 items-center justify-center rounded-full border border-border-strong px-2 text-small font-semibold tabular-nums"
                  >
                    {live.length}
                  </span>
                )}
              </h2>
              <p className={subtitle}>{approvalsPageCopy.waitingSubtitle}</p>
              {cards.length === 0 ? (
                <p className="m-0 mt-4 rounded-lg border border-border bg-surface-raised px-6 py-5 text-body text-ink-muted">
                  {approvalsPageCopy.waitingEmpty}
                </p>
              ) : (
                <ul ref={list} className="m-0 mt-4 flex list-none flex-col gap-4 p-0">
                  {cards.map(({ request, held }) => (
                    <ApprovalCard
                      key={request.id}
                      request={request}
                      today={today}
                      timeZone={timeZone}
                      conflict={held?.status}
                      onApprove={(item, button) => decisions.begin('approve', item, button)}
                      onDeny={(item, button) => decisions.begin('deny', item, button)}
                    />
                  ))}
                </ul>
              )}
            </section>

            <section aria-labelledby={comingUpId} className="mt-14">
              <SectionHeading id={comingUpId}>{approvalsPageCopy.comingUp}</SectionHeading>
              <p className={subtitle}>{approvalsPageCopy.comingUpSubtitle}</p>
              {coming.length === 0 ? (
                <p className="m-0 mt-4 border-t border-border-subtle px-3 py-4 text-ui text-ink-muted">
                  {approvalsPageCopy.comingUpEmpty}
                </p>
              ) : (
                <Rows>
                  {coming.map((request) => (
                    <RequestRow key={request.id} variant="team" request={request} />
                  ))}
                </Rows>
              )}
            </section>

            <section aria-labelledby={recentId} className="mt-14">
              <SectionHeading id={recentId}>{approvalsPageCopy.recent}</SectionHeading>
              <p className={subtitle}>{approvalsPageCopy.recentSubtitle}</p>
              {decided.length === 0 ? (
                <p className="m-0 mt-4 border-t border-border-subtle px-3 py-4 text-ui text-ink-muted">
                  {approvalsPageCopy.recentEmpty}
                </p>
              ) : (
                <Rows>
                  {decided.map((request) => (
                    <RequestRow
                      key={request.id}
                      variant="team"
                      request={request}
                      decidedLine={decisionLine(
                        request.status as 'approved' | 'denied',
                        request.decidedAt,
                        today,
                        timeZone,
                      )}
                      noteLabel={approvalsPageCopy.yourNote}
                    />
                  ))}
                </Rows>
              )}
            </section>
          </>
        )}
      </div>

      {decisions.open && (
        <DecisionDialog
          open
          onOpenChange={(next) => {
            if (!next) decisions.goBack()
          }}
          kind={decisions.open.kind}
          person={decisions.open.request.person}
          facts={decisionFacts(decisions.open.request)}
          note={decisions.note}
          onNoteChange={decisions.setNote}
          deciding={decisions.deciding}
          onConfirm={decisions.confirm}
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            const plan = decisions.focusPlan()
            if (plan.to === 'opener') decisions.open?.opener.focus()
            else if (plan.to === 'request') {
              const card = list.current?.querySelector(`[data-request-id="${plan.id}"]`)
              const button = card?.querySelector('button')
              if (button) button.focus()
              else heading.current?.focus()
            } else heading.current?.focus()
          }}
        />
      )}
    </div>
  )
}
