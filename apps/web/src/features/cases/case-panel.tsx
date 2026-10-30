import { useLayoutEffect, useRef } from 'react'
import type { CaseOpenedOut } from '@/api/generated'
import { useGetCaseTexts, useListMyCases } from '@/api/generated'
import { useMe } from '@/app/useMe'
import { EscalationPanel, type EscalationPanelProps } from '@/components/assistant/escalation-panel'
import { CaseForm } from '@/components/cases/case-form'
import { CaseSent } from '@/components/cases/case-sent'
import { MY_CASES_LINK, YOUR_CASES_LINK } from '@/components/cases/labels'
import { useCaseSlots } from './case-slots'
import { isWaiting, WAITING_CASE_LIMIT } from './waiting'
import { useSendCase } from './use-open-case'

type CasePanelProps = Pick<
  EscalationPanelProps,
  'kind' | 'message' | 'contacts' | 'onTryAgain' | 'announceOnMount' | 'writeToHr'
> & {
  /** The turn's ID: null for a live turn that has not been given one yet. */
  turnId: string | null
  /** The turn's own question, word for word: the form's starting words. */
  question: string
  /**
   * The turn is saved and ended without an internal error, so the server holds its verdict and
   * will take a case from it. A live turn's escalation event arrives before the verdict is
   * stored, so a live turn never offers one: its saved copy does.
   */
  ended: boolean
  /** The event's `offerCase`. */
  offerCase: boolean
  /** The case already opened from this turn, on a saved turn. */
  caseOpened: CaseOpenedOut | null
}

/**
 * An HR panel in the conversation, with its case offer. Where the panel may not offer a case yet
 * (the unavailable panel, a turn still running or failed, no turn ID) this is the plain panel.
 * Otherwise `OfferedPanel` runs the offer: the button, the form, the sent line, or the limit line.
 */
export function CasePanel({
  turnId,
  ended,
  offerCase,
  caseOpened,
  question,
  ...panel
}: CasePanelProps) {
  if (!offerCase || !ended || turnId === null || panel.kind === 'unavailable') {
    return <EscalationPanel {...panel} />
  }
  return <OfferedPanel turnId={turnId} caseOpened={caseOpened} question={question} {...panel} />
}

function OfferedPanel({
  turnId,
  caseOpened,
  question,
  ...panel
}: Omit<CasePanelProps, 'ended' | 'offerCase' | 'turnId'> & { turnId: string }) {
  const { data: me } = useMe()
  const isHr = me?.isHrAdmin ?? false
  const texts = useGetCaseTexts()
  const mine = useListMyCases()
  const slot = useCaseSlots((s) => s.slots[turnId])
  const setSlot = useCaseSlots((s) => s.set)
  const clearSlot = useCaseSlots((s) => s.clear)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const returnFocus = useRef(false)

  const send = useSendCase({
    turnId,
    onSent: (sent) => setSlot(turnId, { phase: 'sent', sent }),
    onLimit: () => setSlot(turnId, { phase: 'limit' }),
    // The conversation read again carries the case, and its saved turn shows the sent line.
    onAlreadySent: () => clearSlot(turnId),
  })

  // "Not now" puts the button back, and focus goes to it.
  useLayoutEffect(() => {
    if (slot === undefined && returnFocus.current) {
      returnFocus.current = false
      buttonRef.current?.focus()
    }
  }, [slot])

  const waiting = (mine.data?.items ?? []).filter(isWaiting).length
  const limitLine = texts.data?.waitingLimit
  // HR has no My cases page, so HR is given no link anywhere.
  const sentLink = isHr ? null : MY_CASES_LINK
  const limitLink = isHr ? null : YOUR_CASES_LINK

  let caseArea = null
  let crisisText: string | null = null
  if (slot?.phase === 'sent') {
    caseArea = (
      <CaseSent variant="panel" state="sent" sentLine={slot.sent.sentLine} link={sentLink} />
    )
    crisisText = slot.sent.crisisText
  } else if (caseOpened !== null) {
    // A reload: the same line from the saved turn, which does not take focus.
    caseArea = (
      <CaseSent
        variant="panel"
        state="sent"
        sentLine={caseOpened.sentLine}
        link={sentLink}
        focusOnMount={false}
      />
    )
  } else if (slot?.phase === 'limit' && limitLine) {
    caseArea = (
      <CaseSent variant="panel" state="limit" limitLine={limitLine} link={limitLink} focusOnMount />
    )
  } else if (slot?.phase === 'open' && texts.data) {
    caseArea = (
      <CaseForm
        variant="panel"
        bullets={texts.data.bullets}
        prefill={question}
        sending={send.sending}
        sendFailed={send.sendFailed}
        refusal={send.refusal}
        onSend={send.send}
        onCancel={() => {
          returnFocus.current = true
          send.reset()
          clearSlot(turnId)
        }}
      />
    )
  } else if (waiting >= WAITING_CASE_LIMIT && limitLine) {
    caseArea = <CaseSent variant="panel" state="limit" limitLine={limitLine} link={limitLink} />
  }

  return (
    <>
      <EscalationPanel
        {...panel}
        // Nothing new shows until the form's texts are here, so no button leads nowhere.
        offerCase={caseArea !== null || texts.data !== undefined}
        onOpenCase={() => {
          send.reset()
          setSlot(turnId, { phase: 'open' })
        }}
        openCaseRef={buttonRef}
        caseArea={caseArea}
      />
      {crisisText !== null && panel.kind === 'sensitive' && (
        <EscalationPanel
          kind="crisis"
          message={crisisText}
          contacts={panel.contacts}
          announceOnMount
        />
      )}
    </>
  )
}
