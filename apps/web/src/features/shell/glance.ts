import type { SummaryOut } from '@/api/generated'
import type { GlanceItem } from '@/components/status/glance-list'
import { splitLabel } from '@/components/timeoff/label-parts'

/** "1 request pending", "2 requests pending": the figure's own count picks the form. */
const plural = (count: number, one: string, many: string) => (count === 1 ? one : many)

/**
 * The time-off figures for the rail's "At a glance" list, from `GET /time-off/summary`: PTO
 * available, requests pending and approvals waiting for a manager (each with the marker when any
 * are). The PTO figure is the API's label split at its parenthesis, so the days stay off the card
 * and nothing is worked out here.
 */
export function timeOffGlance(summary: SummaryOut): GlanceItem[] {
  const items: GlanceItem[] = [
    {
      id: 'pto-available',
      value: splitLabel(summary.ptoAvailableLabel).hours,
      label: 'PTO available',
      destination: 'Time off',
      to: '/time-off',
    },
    {
      id: 'requests-pending',
      value: String(summary.pendingCount),
      label: plural(summary.pendingCount, 'request pending', 'requests pending'),
      destination: 'Time off',
      to: '/time-off',
      marker: summary.pendingCount > 0,
    },
  ]
  if (summary.waitingCount !== null) {
    items.push({
      id: 'approvals-waiting',
      value: String(summary.waitingCount),
      label: plural(summary.waitingCount, 'approval waiting', 'approvals waiting'),
      destination: 'Approvals',
      to: '/approvals',
      marker: summary.waitingCount > 0,
    })
  }
  return items
}
