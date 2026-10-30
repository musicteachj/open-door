import { useQueryClient } from '@tanstack/react-query'
import { useLayoutEffect, useRef, useState } from 'react'
import { useOpenCase, type CaseSentOut } from '@/api/generated'
import type { CaseFormProps } from '@/components/cases/case-form'
import { ApiError } from '@/lib/api-fetch'
import { invalidateAfterSend } from './invalidate'

type Input = Parameters<CaseFormProps['onSend']>[0]

type Options = {
  /** The flagged turn the case is opened from, or none (My cases). */
  turnId?: string
  /** The case was sent (or a repeat of the same send: the server returns the same case). */
  onSent: (sent: CaseSentOut) => void
  /** The server says five cases are already waiting. */
  onLimit: () => void
  /**
   * The server already has a case for this form's `submissionId` (an earlier send got through and
   * its answer was lost). The form should close, and the data read again shows the case.
   */
  onAlreadySent: () => void
}

/**
 * Sends one case for a form. Only one send runs at a time: a ref ignores a second press made
 * before the page has drawn "Sending…" (the form reuses one `submissionId`, and the server would
 * return the same case, but there is no reason to ask twice). Whatever happens, the case lists and
 * the conversation are read again; the server's answer is never written into the cache.
 *
 * What went wrong is told to the form: the server's own refusals of the words (`refusal`), the
 * waiting limit (`onLimit`), a send the server already holds (`onAlreadySent`), and everything else as `sendFailed`, which keeps the words and offers
 * "Try again". The callbacks are on the mutation hook, not on each `mutate`, so they still run if
 * the form's component is swapped out while the request is out (the live turn settling).
 */
export function useSendCase({ turnId, onSent, onLimit, onAlreadySent }: Options) {
  const queryClient = useQueryClient()
  const busy = useRef(false)
  const latest = useRef({ onSent, onLimit, onAlreadySent })
  useLayoutEffect(() => {
    latest.current = { onSent, onLimit, onAlreadySent }
  })
  const [sendFailed, setSendFailed] = useState(false)
  const [refusal, setRefusal] = useState<CaseFormProps['refusal']>(null)

  const mutation = useOpenCase({
    mutation: {
      onSuccess: (sent) => {
        if (!sent) {
          setSendFailed(true)
          return
        }
        latest.current.onSent(sent)
      },
      onError: (error) => {
        if (error instanceof ApiError) {
          const type = error.problem?.type
          if (error.status === 409 && type === 'case-waiting-limit') {
            latest.current.onLimit()
            return
          }
          if (error.status === 409 && type === 'case-submission-conflict') {
            latest.current.onAlreadySent()
            return
          }
          if (error.status === 422 && type === 'case-personal-data') {
            setRefusal('personal-data')
            return
          }
          if (error.status === 422 && type === 'case-empty-words') {
            setRefusal('empty')
            return
          }
        }
        setSendFailed(true)
      },
      onSettled: async () => {
        try {
          await invalidateAfterSend(queryClient)
        } finally {
          busy.current = false
        }
      },
    },
  })

  return {
    /** Forgets an earlier refusal or failure, as the form closes or opens again. */
    reset: () => {
      setSendFailed(false)
      setRefusal(null)
    },
    sending: mutation.isPending,
    sendFailed,
    refusal,
    send: ({ submissionId, category, text }: Input) => {
      if (busy.current) return
      busy.current = true
      setSendFailed(false)
      setRefusal(null)
      mutation.mutate({ data: { submissionId, category, text, turnId } })
    },
  }
}
