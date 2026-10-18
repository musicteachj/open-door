import { Banner } from '@/components/feedback/banner'
import { Button } from '@/components/ui/button'
import { Segments } from './crisis-segments'
import { linkifyEmergency } from './crisis-text'
import { conversationCopy } from './labels'

type BudgetBannerProps = {
  /** `sandbox`: this sandbox's assistant budget is used. `daily`: the day's demo budget is. */
  kind: 'sandbox' | 'daily'
  /**
   * The API's text for this stop, shown as written. It names 911 and 988, so it is never worded
   * here. "call 911" and "call or text 988" become `tel:` links, and no word changes.
   */
  message: string
  /** Sandbox only. A new sandbox starts with a fresh budget. */
  onStartNewSandbox?: () => void
  className?: string
}

/**
 * The full-width banner across the top of the sheet when the assistant is out of budget (from the
 * design's Conversation frames). It is the app's `Banner`, with its warning icon and polite
 * status, and it can't be dismissed, because the composer stays off until the budget is back. The
 * sandbox kind offers "Start a new sandbox" and the daily kind has nothing to do but wait.
 */
function BudgetBanner({ kind, message, onStartNewSandbox, className }: BudgetBannerProps) {
  return (
    <Banner
      message={<Segments segments={linkifyEmergency(message)} />}
      className={className}
      action={
        kind === 'sandbox' && onStartNewSandbox ? (
          <Button variant="secondary" size="sm" onClick={onStartNewSandbox} className="shrink-0">
            {conversationCopy.startNewSandbox}
          </Button>
        ) : undefined
      }
    />
  )
}

export { BudgetBanner }
export type { BudgetBannerProps }
