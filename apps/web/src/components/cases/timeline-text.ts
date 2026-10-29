import type { TimelineEntryOut } from '@/api/generated'
import { firstNameOf } from './labels'

function actorName(entry: TimelineEntryOut): string {
  const name = [entry.actorGivenName, entry.actorFamilyName].filter(Boolean).join(' ')
  return name || 'HR'
}

/** One event as a sentence: "Dana Whitfield read Priya's words". Null for a kind this doesn't know. */
export function timelineEntryText(
  entry: TimelineEntryOut,
  { personName }: { personName: string },
): string | null {
  switch (entry.kind) {
    case 'opened':
      return `Sent by ${personName}`
    case 'summary_written':
      return 'AI summary written'
    case 'summary_failed':
      return 'AI summary couldn’t be written'
    case 'viewed':
      return `${actorName(entry)} read the AI summary`
    case 'text_read':
      return `${actorName(entry)} read ${firstNameOf(personName)}’s words`
    case 'status_changed':
      if (entry.toStatus === 'in_review') return `${actorName(entry)} started the review`
      if (entry.toStatus === 'closed') return `${actorName(entry)} closed the case`
      return `${actorName(entry)} changed the status`
    default:
      return null
  }
}
