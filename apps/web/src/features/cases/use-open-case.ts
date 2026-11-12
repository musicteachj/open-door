import { useQueryClient } from '@tanstack/react-query'
import { useLayoutEffect, useRef, useState } from 'react'
import { useOpenCase, type CaseSentOut } from '@/api/generated'
import type { CaseFormProps } from '@/components/cases/case-form'
import { ApiError } from '@/lib/api-fetch'
import { invalidateAfterSend } from './invalidate'

/**
 * The 422s and 404s a retry can't change (`about:blank` is the API's own validation 422). A 422
 * that isn't the API's problem (a proxy's page) keeps "Try again".
 */
const CANNOT_SEND_422: ReadonlySet<string> = new Set(['about:blank', 'case-invalid'])
const CANNOT_SEND_404: ReadonlySet<string> = new Set(['case-turn-not-found', 'case-not-found'])

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
  /**
   * The server refused the form or the message in a way a retry cannot change (an invalid form,
   * a turn that can't start a case, a case that is not found). The form should close and say so.
   */
  onCannotSend: () => void
}

/**
 * Sends one case for a form. Only one send runs at a time: a ref ignores a second press made
 * before the page has drawn "Sending…" (the form reuses one `submissionId`, and the server would
 * return the same case, but there is no reason to ask twice). Whatever happens, the case lists and
 * the conversation are read again (without holding the send pending); the server's answer is never written into the cache.
 *
 * What went wrong is told to the form: the server's own refusals of the words (`refusal`), the
 * waiting limit (`onLimit`), a send the server already holds (`onAlreadySent`), a refusal no retry
 * can fix (`onCannotSend`), and everything else as `sendFailed`, which keeps the words and offers
 * "Try again". The callbacks are on the mutation hook, not on each `mutate`, so they still run if
 * the form's component is swapped out while the request is out (the live turn settling).
 */
export function useSendCase({ turnId, onSent, onLimit, onAlreadySent, onCannotSend }: Options) {
  const queryClient = useQueryClient()
  const busy = useRef(false)
  const latest = useRef({ onSent, onLimit, onAlreadySent, onCannotSend })
  useLayoutEffect(() => {
    latest.current = { onSent, onLimit, onAlreadySent, onCannotSend }
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
          // The server's own words for the box, so the person can shorten them and send again.
          if (error.status === 422 && type === 'case-words-too-long' && error.problem?.detail) {
            setRefusal({ kind: 'too-long', message: error.problem.detail })
            return
          }
          // Refusals a retry can't change: the generic validation 422 (`about:blank`), an invalid
          // form, a turn that can't start a case, or a case that isn't found.
          if (
            (error.status === 422 && CANNOT_SEND_422.has(type ?? '')) ||
            (error.status === 404 && CANNOT_SEND_404.has(type ?? ''))
          ) {
            latest.current.onCannotSend()
            return
          }
        }
        setSendFailed(true)
      },
      onSettled: () => {
        // Not awaited: the mutation must stop being pending when the answer is in, or the form
        // stays disabled (and a refusal cannot move focus into it) until the lists are read again.
        busy.current = false
        void invalidateAfterSend(queryClient)
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
