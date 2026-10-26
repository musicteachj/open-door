import { useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { useCancelProposal, useConfirmProposal } from '@/api/generated'
import { invalidateTimeOff } from '@/features/time-off/use-time-off'
import { ApiError } from '@/lib/api-fetch'

/**
 * What went wrong with a press, for the card to say calmly. `gone`: the server has no such
 * proposal for this person (a 404), so nothing can be done with the card. `failed`: the press did
 * not get through (the network, a 5xx), so nothing was changed and the person may try again. A 409
 * is neither: it says the card has already moved on, and the next read shows how.
 */
export type ProposalProblem = 'gone' | 'failed'

/**
 * Confirm and Dismiss for one card, through the generated mutations. The card's own state (the
 * note being typed, the "pressed" focus rule) lives in the component. This never writes the
 * server's answer into the cache: whatever happens, the conversation and the time-off queries are
 * read again, and the card shows what that read says. `confirming` stays true until that read
 * lands, so Confirm does not flicker back on a card that is about to change.
 */
export function useProposalActions(proposalId: string) {
  const queryClient = useQueryClient()
  const [problem, setProblem] = useState<ProposalProblem | null>(null)
  // One press at a time. A ref, not the mutations' `isPending`: two clicks before the page draws
  // again would both see the old render's `false`.
  const busy = useRef(false)
  const mutation = {
    onMutate: () => setProblem(null),
    onError: (error: Error) => {
      if (error instanceof ApiError && error.status === 409) return
      setProblem(error instanceof ApiError && error.status === 404 ? 'gone' : 'failed')
    },
    onSettled: async () => {
      try {
        await invalidateTimeOff(queryClient)
      } finally {
        busy.current = false
      }
    },
  }
  const confirmation = useConfirmProposal({ mutation })
  const dismissal = useCancelProposal({ mutation })

  return {
    problem,
    confirming: confirmation.isPending,
    dismissing: dismissal.isPending,
    /** `note` is a denial's note, or null for any other card or a denial with none. */
    confirm: (note: string | null) => {
      if (busy.current) return
      busy.current = true
      confirmation.mutate({ proposalId, data: note === null ? undefined : { note } })
    },
    dismiss: () => {
      if (busy.current) return
      busy.current = true
      dismissal.mutate({ proposalId })
    },
  }
}
