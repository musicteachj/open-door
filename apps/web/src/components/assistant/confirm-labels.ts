// The confirm card's words and accessible names (screen 10), in one tested place. The web app
// writes them from the card's structured data; none comes from the model or the server's prose.
// No pronouns: a line names the person or the page.
import type { CanceledReason, Card, ProposalStatus } from '@/api/generated'
import { formatterFor } from '@/lib/time'
import { firstNameOf } from '@/components/approvals/labels'
import { longRange } from '@/components/timeoff/dates'
import { splitLabel } from '@/components/timeoff/label-parts'
import { typeLabel, type TimeOffStatus } from '@/components/timeoff/labels'

export const confirmCopy = {
  proposed: 'Proposed by the AI. Nothing happens until you confirm.',
  confirm: 'Confirm',
  deny: 'Deny',
  confirming: 'Confirming…',
  dismiss: 'Dismiss',
  dismissing: 'Dismissing…',
  wait: 'Wait for the answer to finish',
  askAgain: 'Ask again',
  viewTimeOff: 'View in Time off',
  viewApprovals: 'View in Approvals',
  yourNote: 'Your note',
  // The same words as the server's generic failure text.
  unknownFailure: 'This card could not be completed.',
  factType: 'Type',
  factDates: 'Dates',
  factAmount: 'Amount',
  factBalance: 'Balance',
  factStatus: 'Status',
  sickInfo:
    'Sick time is recorded right away, with no approval. Your manager will see it in Coming up.',
  expires: (time: string) => `Expires at ${time}`,
  amountGoBack: (label: string) =>
    `${label} ${splitLabel(label).hours === '1 hour' ? 'goes' : 'go'} back`,
} as const

/** "3:42 PM": the moment in the given zone. Static text, never a ticking timer. */
export function expiryLabel(expiresAt: string, timeZone: string): string {
  return (
    formatterFor(timeZone, { hour: 'numeric', minute: '2-digit' })
      .format(new Date(expiresAt))
      // Newer ICU writes a narrow no-break space before AM and PM.
      .replace(/[  ]/g, ' ')
  )
}

export function cardTitle(card: Card): string {
  if (card.kind === 'request') return card.type === 'sick' ? 'Record sick time' : 'Book PTO'
  if (card.kind === 'decide')
    return card.decision === 'deny' ? 'Deny a request' : 'Approve a request'
  return 'Cancel time off'
}

export function confirmLabel(card: Card): string {
  return card.kind === 'decide' && card.decision === 'deny' ? confirmCopy.deny : confirmCopy.confirm
}

/** The verb in "Couldn't book this": book, record, approve, deny, or cancel. */
export function failureVerb(card: Card): string {
  if (card.kind === 'request') return card.type === 'sick' ? 'record' : 'book'
  if (card.kind === 'decide') return card.decision
  return 'cancel'
}

/** What the action is, for the buttons' names: "book PTO on Friday, October 30". */
function actionPhrase(card: Card): string {
  const dates = longRange(card.startDate, card.endDate)
  if (card.kind === 'request') {
    return `${card.type === 'sick' ? 'record sick time' : 'book PTO'} on ${dates}`
  }
  if (card.kind === 'decide') return `${card.decision} ${card.requester.name}’s PTO, ${dates}`
  return `cancel ${typeLabel(card.type, { lower: true })} on ${dates}`
}

/** "Confirm: book PTO on Friday, October 30". */
export function confirmName(card: Card): string {
  return `Confirm: ${actionPhrase(card)}`
}

/** "Dismiss, don’t book PTO on Friday, October 30"; on a cancel card, "Dismiss, keep PTO on ...". */
export function dismissName(card: Card): string {
  if (card.kind === 'cancel') {
    return `Dismiss, keep ${typeLabel(card.type, { lower: true })} on ${longRange(card.startDate, card.endDate)}`
  }
  return `Dismiss, don’t ${actionPhrase(card)}`
}

/** The line on an executed card. `withNote` is for a denial that carried a note. */
export function executedText(
  card: Card,
  { withNote = false }: { withNote?: boolean } = {},
): string {
  if (card.kind === 'request') {
    if (card.type === 'sick') return 'Recorded.'
    return card.approver ? `Requested. ${card.approver.name} will review it.` : 'Requested.'
  }
  if (card.kind === 'decide') {
    const first = firstNameOf(card.requester.name)
    if (card.decision === 'approve') return `Approved. ${first} will see it on the Time off page.`
    return withNote
      ? `Denied. ${first} will see your note on the Time off page.`
      : `Denied. ${first} will see it on the Time off page.`
  }
  if (card.type === 'sick') return 'Canceled. The sick time is no longer recorded.'
  // Nothing goes back when the days were before the balance began, so no figure is claimed.
  if (card.returnsLabel === null || !card.returnsMinutes) return 'Canceled.'
  const hours = splitLabel(card.returnsLabel).hours
  return `Canceled. ${hours} ${hours === '1 hour' ? 'is' : 'are'} back in your balance.`
}

/** The neutral line on a card that ended without a change. */
export function endedText(status: ProposalStatus, reason: CanceledReason | null): string {
  if (status === 'expired') return 'This card expired after 15 minutes. Nothing was changed.'
  if (reason === 'replaced') return 'Replaced by a newer card. Nothing was changed.'
  if (reason === 'turn-incomplete') return 'This card’s answer didn’t finish. Nothing was changed.'
  return 'You dismissed this. Nothing was changed.'
}

/** The badge in the header once a card is executed. */
export function executedBadge(card: Card): TimeOffStatus {
  if (card.kind === 'request') return card.type === 'sick' ? 'recorded' : 'waiting'
  if (card.kind === 'decide') return card.decision === 'deny' ? 'denied' : 'approved'
  return 'canceled'
}
