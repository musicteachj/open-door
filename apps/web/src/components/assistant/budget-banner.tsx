import { Link } from 'react-router'
import { Banner } from '@/components/feedback/banner'
import { Button } from '@/components/ui/button'
import { WalkthroughLink } from '@/components/walkthrough/walkthrough-link'
import { APP_LINK } from './link-class'
import type { PageLink } from '@/lib/page-link'
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
  /** "Write to HR", after the text. A person gets it; HR gets null, as HR has no My cases. */
  writeToHr?: PageLink | null
  className?: string
}

/**
 * The full-width banner across the top of the sheet when the assistant is out of budget (from the
 * design's Conversation frames). It is the app's `Banner`, with its warning icon and polite
 * status, and it can't be dismissed, because the composer stays off until the budget is back. The
 * sandbox kind offers "Start a new sandbox"; the daily kind links the recorded walkthrough.
 */
function BudgetBanner({
  kind,
  message,
  onStartNewSandbox,
  writeToHr = null,
  className,
}: BudgetBannerProps) {
  return (
    <Banner
      message={
        <>
          <span data-slot="budget-text">
            <Segments segments={linkifyEmergency(message)} />
          </span>
          {writeToHr && (
            <>
              {' '}
              <Link to={writeToHr.to} className={APP_LINK}>
                {writeToHr.label}
              </Link>
            </>
          )}
          {/* ADR 0019: at the day's limit the demo offers the recorded walkthrough, on its own line
              under the approved text. A new sandbox doesn't help then, so only the daily kind. */}
          {kind === 'daily' && (
            <>
              {' '}
              {/* 8 px above, so its 24 px target circle clears "Write to HR" on the line above
                  (WCAG 2.5.8; at 4 px Linux's fonts put them under 24 px apart). */}
              <span className="mt-2 block">
                <WalkthroughLink />
              </span>
            </>
          )}
        </>
      }
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
