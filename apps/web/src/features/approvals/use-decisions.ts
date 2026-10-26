import { useEffect, useRef, useState } from 'react'
import type { DecisionBody, RequestOut, RequestOutStatus } from '@/api/generated'
import {
  approvalsPageCopy,
  approvedToast,
  deniedToast,
  firstNameOf,
} from '@/components/approvals/labels'
import { trimLikePython } from '@/components/assistant/text-count'
import { useShellToast } from '@/features/shell/toast-store'
import { useDecideTimeOff } from '@/features/time-off/use-time-off'
import { ApiError } from '@/lib/api-fetch'

type Kind = 'approve' | 'deny'
type Open = { kind: Kind; request: RequestOut; opener: HTMLElement }
/** A card that was seen waiting and has moved on, kept in its place until the next visit. */
export type Held = { request: RequestOut; status: RequestOutStatus }
/** Where focus goes when the dialog is gone. */
type FocusPlan = { to: 'opener' } | { to: 'request'; id: string } | { to: 'heading' }

// 'pending' is not here: a refusal that says the request is still pending explains nothing, so it
// is treated like one that names no status.
const STALE: RequestOutStatus[] = ['canceled', 'approved', 'denied', 'recorded']

/** The status a 409 says the request now has, or null when it names none this page knows. */
function currentStatusOf(error: ApiError): RequestOutStatus | null {
  const status = error.problem?.currentStatus
  return STALE.find((known) => known === status) ?? null
}

/** A card's place among the cards: where it was, or the end when it was not among them. */
function slotOf(id: string, order: string[]): number {
  const at = order.indexOf(id)
  return at === -1 ? order.length : at
}

/**
 * Approve and Deny for the Approvals page: which dialog is open, the note, the decision itself,
 * the cards held after a 409, and where focus goes afterward. `layout()` is read when a decision
 * ends, never during a render: `live` is the ids of the cards that can still be decided, in the
 * order the page draws them, which is what "the next request" means, and `order` is every card,
 * held ones too, which is where a held card keeps its place.
 *
 * - Success: the toast, the dialog closes, and focus goes to the next card's Approve (or, with
 *   none left, the heading). The write has already read the queue again by then.
 * - A 409 (canceled, or already decided): the dialog closes and the card is held with its
 *   refusal, so it stays on the page though the queue no longer lists it. Focus goes the same way.
 *   A 409 that names no status the page knows holds nothing: a toast with the refusal, and the
 *   card stays only if the read again still lists it.
 * - Any other failure changes nothing: a calm toast, and the dialog stays for another try.
 *
 * Toasts are keyed to the manager (`personId`), so one that lands after a persona switch never
 * shows to the new person.
 */
export function useDecisions({
  personId,
  layout,
}: {
  personId: string
  layout: () => { live: string[]; order: string[] }
}) {
  const [open, setOpen] = useState<Open | null>(null)
  const [note, setNote] = useState('')
  const [held, setHeld] = useState<(Held & { index: number })[]>([])
  // The refusal is handled here, before time off is read again: the card that was seen waiting is
  // held the moment the server says it has moved on, so the read that follows never takes it away
  // for even one draw.
  const current = useRef<Open | null>(null)
  const layoutNow = useRef(layout)
  // Every card, in the order the page drew them when the decision started: a held card keeps that
  // place, though the page may have drawn without it by the time the refusal arrives.
  const orderAtStart = useRef<string[]>([])
  useEffect(() => {
    layoutNow.current = layout
  })
  const decide = useDecideTimeOff((error) => {
    const request = current.current?.request
    if (request === undefined || !(error instanceof ApiError) || error.status !== 409) return
    // A refusal that names no status leaves the card as it is: the read that follows says whether
    // it still waits.
    const status = currentStatusOf(error)
    if (status === null) return
    setHeld((all) => [
      ...all.filter((item) => item.request.id !== request.id),
      {
        request,
        status,
        index: slotOf(request.id, orderAtStart.current),
      },
    ])
  })
  const plan = useRef<FocusPlan>({ to: 'opener' })
  // One decision at a time. A ref, not the mutation's `isPending`, which two quick presses both
  // read as false before the page draws again.
  const busy = useRef(false)

  // `live` is the order the cards had when the decision started: the queue is read again before
  // the write ends, and by then the decided card may be gone from the page's own order.
  const nextAfter = (id: string, live: string[]): FocusPlan => {
    const at = live.indexOf(id)
    const next = live[at + 1] ?? live[at - 1]
    return next === undefined ? { to: 'heading' } : { to: 'request', id: next }
  }

  function begin(kind: Kind, request: RequestOut, opener: HTMLElement) {
    setNote('')
    plan.current = { to: 'opener' }
    const next = { kind, request, opener }
    current.current = next
    setOpen(next)
  }

  function goBack() {
    if (decide.isPending) return
    plan.current = { to: 'opener' }
    setOpen(null)
  }

  async function confirm() {
    if (open === null || busy.current) return
    busy.current = true
    const { kind, request } = open
    const { live: before, order } = layoutNow.current()
    orderAtStart.current = order
    const text = kind === 'deny' ? trimLikePython(note) : ''
    const data: DecisionBody = text === '' ? { decision: kind } : { decision: kind, note: text }
    const first = firstNameOf(request.person.name)
    try {
      await decide.mutateAsync({ requestId: request.id, data })
      useShellToast
        .getState()
        .show(kind === 'approve' ? approvedToast(first) : deniedToast(first, text !== ''), personId)
      plan.current = nextAfter(request.id, before)
      setOpen(null)
    } catch (error) {
      if (error instanceof ApiError && error.status === 409 && currentStatusOf(error) !== null) {
        plan.current = nextAfter(request.id, before)
        setOpen(null)
      } else if (error instanceof ApiError && (error.status === 404 || error.status === 409)) {
        // Gone altogether, or changed in a way the page can't name: the queue has been read
        // again, and the card is in it only if it still waits.
        useShellToast
          .getState()
          .show(error.problem?.detail || approvalsPageCopy.changedMeanwhile, personId)
        plan.current = nextAfter(request.id, before)
        setOpen(null)
      } else {
        useShellToast.getState().show(approvalsPageCopy.decisionFailed, personId)
      }
    } finally {
      busy.current = false
    }
  }

  return {
    open,
    note,
    setNote,
    deciding: decide.isPending,
    held,
    begin,
    goBack,
    confirm: () => void confirm(),
    /** Where focus goes once the dialog is gone. */
    focusPlan: () => plan.current,
  }
}
