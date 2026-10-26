import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import type { ProposalOut } from '@/api/generated'
import { ConfirmCard } from '@/components/assistant/confirm-card'
import { trimLikePython } from '@/components/assistant/text-count'
import { FormMessage } from '@/components/timeoff/form-message'
import { useChatStore } from './store'
import { focusComposer } from './use-assistant-composer'
import { invalidateConversation } from './use-conversation'
import { useMe } from '@/app/useMe'
import { browserTimeZone, yearNow } from './proposal-time'
import { useProposalActions } from './use-proposal-actions'

// The confirm cards under an assistant message (screen 10). Each is a `ConfirmCard` wired to the
// server: Confirm and Dismiss call the routes, and the state the card shows always comes from the
// conversation read, never from the answer to a press.

/** What a card says when the server has no such card for this person (a 404). */
const UNAVAILABLE = 'This card is no longer available.'
const SERVER_PROBLEM = 'That didn’t go through. Nothing was changed. You can try again.'

/** The longest delay `setTimeout` takes; a card lives 15 minutes, so this only guards the edge. */
const LONGEST_TIMER_MS = 2 ** 31 - 1
const EXPIRY_RETRIES = 3
const EXPIRY_RETRY_MS = 2000

type ProposalCardProps = {
  proposal: ProposalOut
  /** The question that made the card: "Ask again" puts it back in the composer. */
  question: string
  /** The card's turn is still being answered (a live turn). A stored card says so itself. */
  turnRunning?: boolean
}

function ProposalCard({ proposal, question, turnRunning }: ProposalCardProps) {
  const queryClient = useQueryClient()
  const actions = useProposalActions(proposal.id)
  const [note, setNote] = useState('')
  const timeZone = useMemo(() => browserTimeZone(), [])
  // "This year" is the year at the person's own location, as the Time off page reads it.
  const { data: me } = useMe()
  const locationZone = me?.location.timezone ?? timeZone
  const { card, status, expiresAt } = proposal
  const denial = card.kind === 'decide' && card.decision === 'deny'
  const pending = status === 'pending'

  // Nothing on the card ticks. At the moment it expires the conversation is read again, so the
  // server's read marks it expired and the card turns into its "Ask again" state.
  useEffect(() => {
    if (!pending) return
    const wait = Math.max(0, Date.parse(expiresAt) - Date.now())
    // If the browser's clock runs ahead of the server's, the read at this moment can still say
    // pending. Each read is followed by another 2 seconds later, up to 3 more times. A read that
    // shows the card ended turns `pending` off, which clears the timer.
    let retries = 0
    let timer: ReturnType<typeof setTimeout>
    const read = () => {
      void invalidateConversation(queryClient)
      if (retries++ < EXPIRY_RETRIES) timer = setTimeout(read, EXPIRY_RETRY_MS)
    }
    timer = setTimeout(read, Math.min(wait, LONGEST_TIMER_MS))
    return () => clearTimeout(timer)
  }, [pending, expiresAt, queryClient])

  // The server has no such card for this person: say so on the card, in its own failure line.
  const gone = actions.problem === 'gone' && pending
  return (
    <div className="flex flex-col gap-3">
      <ConfirmCard
        card={card}
        status={gone ? 'failed' : status}
        canceledReason={proposal.canceledReason}
        failure={gone ? { code: 'unavailable', text: UNAVAILABLE } : proposal.failure}
        expiresAt={expiresAt}
        timeZone={timeZone}
        turnRunning={turnRunning ?? proposal.turnRunning}
        confirming={actions.confirming}
        note={note}
        onNoteChange={setNote}
        deniedNote={proposal.deniedNote}
        thisYear={yearNow(locationZone)}
        timeOffHref="/time-off"
        approvalsHref="/approvals"
        onConfirm={() => actions.confirm(denial && trimLikePython(note) !== '' ? note : null)}
        onDismiss={actions.dismiss}
        onAskAgain={() => {
          useChatStore.getState().setDraft(question)
          focusComposer()
        }}
      />
      {actions.problem === 'failed' && pending && (
        <FormMessage tone="refusal">{SERVER_PROBLEM}</FormMessage>
      )}
    </div>
  )
}

/**
 * The cards of one turn, under its message and kept to the assistant column's 680 px. They sit
 * closer to the message than the thread's own gap, since the message's one line introduces them.
 */
export function ProposalCards({
  proposals,
  question,
  turnRunning,
}: {
  proposals: readonly ProposalOut[]
  question: string
  turnRunning?: boolean
}) {
  if (proposals.length === 0) return null
  return (
    <div data-slot="proposal-cards" className="-mt-3 flex w-full max-w-[680px] flex-col gap-3">
      {proposals.map((proposal) => (
        <ProposalCard
          key={proposal.id}
          proposal={proposal}
          question={question}
          turnRunning={turnRunning}
        />
      ))}
    </div>
  )
}
