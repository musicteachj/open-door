import { useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { useParams } from 'react-router'
import { useChangeCaseStatus, type CaseDetailOut, type Status } from '@/api/generated'
import { useMe, type SignedInMe } from '@/app/useMe'
import { CaseDetailHeader } from '@/components/cases/case-detail-header'
import { CaseOwnNotice } from '@/components/cases/case-own-notice'
import { CasePersonCard } from '@/components/cases/case-person-card'
import { CaseStatusActions } from '@/components/cases/case-status-actions'
import { CaseStatusDialog } from '@/components/cases/case-status-dialog'
import { CaseSummaryBlock } from '@/components/cases/case-summary-block'
import { CaseTimeline } from '@/components/cases/case-timeline'
import { CaseWordsReveal } from '@/components/cases/case-words-reveal'
import { detailCopy, firstNameOf, pagesCopy } from '@/components/cases/labels'
import { todayIn } from '@/components/cases/today'
import { PageHeader } from '@/components/core/page-header'
import { LoadingStatus } from '@/components/feedback/loading-status'
import { Skeleton } from '@/components/ui/skeleton'
import { NotFound } from '@/features/global-states/pages'
import { PageSandboxIndicator } from '@/features/shell/page-sandbox-indicator'
import { useShellToast } from '@/features/shell/toast-store'
import { ApiError } from '@/lib/api-fetch'
import { invalidateCases } from './invalidate'
import { isNoSuchCase, useCaseDetail } from './use-case-reads'

// A case at /cases/:caseId, from docs/design/screens/12-hr-cases, for HR. The person's directory
// card, the AI summary, the words (hidden until HR opens them), the status actions, and the
// timeline. Opening the summary or the words is an audited read: see `useCaseDetail`. HR's own
// case shows its header and a notice and nothing else. Anyone but HR gets the Not found page.

export function CaseDetailPage() {
  const { data: me } = useMe()
  const { caseId } = useParams()
  if (!me) return null
  if (!me.isHrAdmin || !caseId) return <NotFound />
  // Keyed by the case, so another case never starts with this one's words or summary.
  return <CaseDetail key={caseId} caseId={caseId} me={me} />
}

type Dialog = 'review' | 'close' | null
type FocusTarget = 'start' | 'close' | 'heading'

function CaseDetail({ caseId, me }: { caseId: string; me: SignedInMe }) {
  const reads = useCaseDetail(caseId, me.id)
  const { detail } = reads
  const queryClient = useQueryClient()
  const [dialog, setDialog] = useState<Dialog>(null)
  const startRef = useRef<HTMLButtonElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const returnTo = useRef<FocusTarget>('start')
  const change = useChangeCaseStatus()

  if (isNoSuchCase(reads.query.error)) {
    return <NotFound />
  }

  const timeZone = me.location.timezone

  function confirm() {
    if (!detail || !dialog || change.isPending) return
    const to: Status = dialog === 'review' ? 'in_review' : 'closed'
    change.mutate(
      { caseId, data: { to } },
      {
        onSuccess: () => {
          if (to === 'closed') reads.words.hide()
          returnTo.current = to === 'closed' ? 'heading' : 'close'
          setDialog(null)
          void invalidateCases(queryClient)
        },
        onError: (error) => {
          const type = error instanceof ApiError ? error.problem?.type : undefined
          setDialog(null)
          if (type === 'words-not-read') {
            // The server has no read of these words by this person: lock until there is one.
            reads.relock()
          } else if (type === 'case-status-refused') {
            useShellToast.getState().show(detailCopy.statusMoved, me.id)
          } else {
            useShellToast.getState().show(detailCopy.statusFailed, me.id)
          }
          void invalidateCases(queryClient)
        },
      },
    )
  }

  return (
    <div className="flex min-w-0 flex-col px-14 pt-10 pb-12 max-[1100px]:px-12 max-[760px]:px-5 max-[760px]:pb-8">
      <div className="w-full max-w-270">
        <PageHeader
          back={{ to: '/cases', label: pagesCopy.back }}
          right={<PageSandboxIndicator />}
        />
        <LoadingStatus loading={!detail} text={pagesCopy.caseLoading} />
        {detail ? (
          <div className="mt-6 flex flex-col gap-6">
            <CaseDetailHeader
              category={detail.category}
              status={detail.status}
              sentAt={detail.sentAt}
              statusChangedAt={detail.statusChangedAt}
              replyBy={detail.replyBy}
              timeZone={timeZone}
              today={todayIn(timeZone)}
              crisis={detail.screening === 'crisis'}
              isOwn={detail.isOwn}
              headingRef={headingRef}
            />
            {detail.isOwn ? (
              <CaseOwnNotice />
            ) : (
              <Body
                detail={detail}
                reads={reads}
                timeZone={timeZone}
                locked={!reads.wordsRead}
                dialog={dialog}
                pending={change.isPending}
                startRef={startRef}
                closeRef={closeRef}
                onOpenDialog={(kind) => {
                  returnTo.current = kind === 'review' ? 'start' : 'close'
                  setDialog(kind)
                }}
                onDialogClosed={() => setDialog(null)}
                onConfirm={confirm}
                onCloseAutoFocus={(event) => {
                  event.preventDefault()
                  const target = { start: startRef, close: closeRef, heading: headingRef }[
                    returnTo.current
                  ]
                  target.current?.focus()
                }}
              />
            )}
          </div>
        ) : (
          <div aria-hidden="true" data-slot="case-skeleton" className="mt-6 flex flex-col gap-4">
            <Skeleton className="h-9 w-96 max-w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        )}
      </div>
    </div>
  )
}

function Body({
  detail,
  reads,
  timeZone,
  locked,
  dialog,
  pending,
  startRef,
  closeRef,
  onOpenDialog,
  onDialogClosed,
  onConfirm,
  onCloseAutoFocus,
}: {
  detail: CaseDetailOut
  reads: ReturnType<typeof useCaseDetail>
  timeZone: string
  locked: boolean
  dialog: Dialog
  pending: boolean
  startRef: React.RefObject<HTMLButtonElement | null>
  closeRef: React.RefObject<HTMLButtonElement | null>
  onOpenDialog: (kind: 'review' | 'close') => void
  onDialogClosed: () => void
  onConfirm: () => void
  onCloseAutoFocus: (event: Event) => void
}) {
  const name = `${detail.givenName ?? ''} ${detail.familyName ?? ''}`.trim()
  const first = firstNameOf(name)
  const { summary, words } = reads
  return (
    <>
      <div className="grid grid-cols-[minmax(0,1fr)_360px] items-start gap-x-10 gap-y-6 max-[900px]:grid-cols-1">
        <div className="flex min-w-0 flex-col gap-6">
          <CasePersonCard
            name={name}
            title={detail.title}
            department={detail.departmentName}
            location={detail.locationName}
            email={detail.workEmail}
          />
          {summary.state !== null && (
            <CaseSummaryBlock
              state={summary.state}
              text={summary.text}
              writtenAt={summary.writtenAt}
              model={summary.model}
              timeZone={timeZone}
              retrying={summary.retrying}
              canRetry={summary.canRetry}
              onRetry={() => void summary.retry()}
            />
          )}
          <CaseWordsReveal
            firstName={first}
            state={words.state}
            words={words.text}
            onShow={() => void words.show()}
            onHide={words.hide}
          />
          <CaseStatusActions
            status={detail.status}
            firstName={first}
            locked={locked}
            startButtonRef={startRef}
            closeButtonRef={closeRef}
            onStartReview={() => onOpenDialog('review')}
            onClose={() => onOpenDialog('close')}
          />
        </div>
        <CaseTimeline
          entries={detail.timeline ?? []}
          screening={detail.screening}
          personName={name}
          timeZone={timeZone}
        />
      </div>
      <CaseStatusDialog
        open={dialog !== null}
        kind={dialog ?? 'review'}
        firstName={first}
        pending={pending}
        onOpenChange={(open) => {
          if (!open && !pending) onDialogClosed()
        }}
        onConfirm={onConfirm}
        onCloseAutoFocus={onCloseAutoFocus}
      />
    </>
  )
}
