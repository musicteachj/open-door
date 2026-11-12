import { useLayoutEffect, useRef, useState } from 'react'
import type { CaseSentOut } from '@/api/generated'
import { useGetCaseTexts, useListMyCases } from '@/api/generated'
import { useMe, type SignedInMe } from '@/app/useMe'
import { EscalationPanel } from '@/components/assistant/escalation-panel'
import { CaseForm } from '@/components/cases/case-form'
import { CaseList } from '@/components/cases/case-list'
import { CaseSent } from '@/components/cases/case-sent'
import { pagesCopy } from '@/components/cases/labels'
import { OpenCaseButton } from '@/components/cases/open-case-button'
import { useCaseDisclosure } from '@/components/cases/use-case-disclosure'
import { PageHeader } from '@/components/core/page-header'
import { LoadingStatus } from '@/components/feedback/loading-status'
import { Skeleton } from '@/components/ui/skeleton'
import { NotFound } from '@/features/global-states/pages'
import { PageSandboxIndicator } from '@/features/shell/page-sandbox-indicator'
import { onlyFirstLoad } from './read-options'
import { useSendCase } from './use-open-case'
import { isWaiting, WAITING_CASE_LIMIT } from './waiting'

// My cases at /my-cases, from docs/design/screens/11-escalation-cases: the cases a person sent HR
// (status only: never their words), and the same confidential-case form as the HR panel, empty.
// HR has no such page, so HR gets the Not found page.

export function MyCasesPage() {
  const { data: me } = useMe()
  if (!me) return null
  if (me.isHrAdmin) return <NotFound />
  return <MyCases me={me} />
}

const NO_CONTACTS: never[] = []

function MyCases({ me }: { me: SignedInMe }) {
  const mine = useListMyCases({ query: { throwOnError: onlyFirstLoad } })
  const texts = useGetCaseTexts()
  // The HR people come with the form's texts, so this page never reads the conversation.
  const contacts = texts.data?.hrContacts ?? NO_CONTACTS
  const disclosure = useCaseDisclosure()
  const { buttonRef } = disclosure
  const [sent, setSent] = useState<CaseSentOut | null>(null)
  // A refusal for the limit holds the line until the list is read again; after that the list's own
  // count decides (a case may have been answered meanwhile). `limitAfter` is when the list was
  // last read as the refusal came.
  const [limitAfter, setLimitAfter] = useState<number | null>(null)
  const readAt = useRef(0)
  useLayoutEffect(() => {
    readAt.current = mine.dataUpdatedAt
  })
  // A refusal no retry can fix replaces the form with a line, until the form is opened again: the
  // open button stays beside it (or, with no cases yet, the empty list and its button).
  const [cannotSend, setCannotSend] = useState(false)
  const send = useSendCase({
    onSent: (result) => {
      setSent(result)
      disclosure.dismiss()
    },
    onLimit: () => {
      setLimitAfter(readAt.current)
      disclosure.dismiss()
    },
    // The list read again shows the case.
    onAlreadySent: disclosure.dismiss,
    onCannotSend: () => {
      setCannotSend(true)
      disclosure.dismiss()
    },
  })

  // A new form starts clean: an earlier refusal or failure is not brought back.
  const openForm = () => {
    send.reset()
    setCannotSend(false)
    disclosure.open()
  }

  const loading = !mine.data
  const cases = mine.data?.items ?? []
  const limitLine = texts.data?.waitingLimit
  const limitReached = limitAfter !== null && mine.dataUpdatedAt === limitAfter
  const atLimit =
    limitLine !== undefined &&
    (limitReached || cases.filter(isWaiting).length >= WAITING_CASE_LIMIT)

  let top = null
  // Set where the "can't be sent" line fills the place, so the list (and its button) shows under it.
  let listUnderTop = false
  if (sent) {
    top = (
      <>
        {/* The lead only: a link to this page would point at itself. */}
        <CaseSent variant="page" state="sent" sentLine={sent.sentLine} link={null} />
        {sent.crisisText !== null && (
          <EscalationPanel
            className="max-w-none"
            kind="crisis"
            message={sent.crisisText}
            contacts={contacts}
            announceOnMount
          />
        )}
      </>
    )
  } else if (disclosure.isOpen && texts.data) {
    top = (
      <CaseForm
        variant="page"
        bullets={texts.data.bullets}
        sending={send.sending}
        sendFailed={send.sendFailed}
        refusal={send.refusal}
        onSend={send.send}
        onCancel={() => {
          send.reset()
          disclosure.close()
        }}
      />
    )
  } else if (atLimit) {
    top = (
      <CaseSent
        variant="page"
        state="limit"
        limitLine={limitLine}
        link={null}
        contacts={contacts}
        focusOnMount={limitAfter !== null}
      />
    )
  } else if (cannotSend && texts.data) {
    listUnderTop = true
    top = (
      <>
        <CaseSent
          variant="page"
          state="cannot-send"
          cannotSendLine={texts.data.cannotSend}
          link={null}
          contacts={contacts}
          focusOnMount
        />
        {cases.length > 0 && (
          <OpenCaseButton ref={buttonRef} onClick={openForm} className="self-start max-sm:w-full" />
        )}
      </>
    )
  } else if (cases.length > 0) {
    top = <OpenCaseButton ref={buttonRef} onClick={openForm} className="self-start max-sm:w-full" />
  }

  // With nothing sent yet the list says so, with the button, unless a form, a sent line, or the
  // limit line already fills that place. Under the "can't be sent" line it shows too, so its button
  // can open the form again.
  const showList = cases.length > 0 || ((top === null || listUnderTop) && !loading)

  return (
    <div className="flex min-w-0 flex-col px-14 pt-10 pb-12 max-[1100px]:px-12 max-[760px]:px-5 max-[760px]:pb-8">
      <div className="w-full max-w-190">
        <PageHeader title={pagesCopy.myCasesTitle} right={<PageSandboxIndicator />} />
        <LoadingStatus loading={loading} text={pagesCopy.myCasesLoading} />
        <p className="m-0 mt-2 max-w-155 text-body-lg text-pretty text-ink-muted">
          {pagesCopy.myCasesIntro}
        </p>
        {loading ? (
          <div
            aria-hidden="true"
            data-slot="my-cases-skeleton"
            className="mt-6 flex flex-col gap-3"
          >
            <Skeleton className="h-10 w-56" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : (
          <div className="mt-6 flex flex-col gap-6">
            {top}
            {showList && (
              <CaseList
                cases={cases}
                timeZone={me.location.timezone}
                onOpenCase={openForm}
                openButtonRef={buttonRef}
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
