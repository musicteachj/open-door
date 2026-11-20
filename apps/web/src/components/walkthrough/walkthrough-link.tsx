import { Link, useLocation } from 'react-router'
import { buttonVariants } from '@/components/ui/button-variants'
import { cn } from '@/lib/utils'
import { WALKTHROUGH_PATH, walkthroughState } from '@/lib/walkthrough-back'

export const WALKTHROUGH_LINK_TEXT = 'Watch the recorded walkthrough'

/** A text link to the recorded walkthrough (14/20, semibold, primary, underlined: screen 16). */
export const WALKTHROUGH_LINK_CLASS =
  'rounded-xs text-ui font-semibold text-primary underline decoration-1 underline-offset-3 hover:text-primary-hover'

/**
 * "Watch the recorded walkthrough", on the landing and under the daily-limit banner. It carries
 * the place it was pressed on, so the page's "Back to the demo" returns there.
 */
export function WalkthroughLink({ className }: { className?: string }) {
  const location = useLocation()
  return (
    <Link
      to={WALKTHROUGH_PATH}
      state={walkthroughState(location)}
      className={cn(WALKTHROUGH_LINK_CLASS, className)}
    >
      {WALKTHROUGH_LINK_TEXT}
    </Link>
  )
}

/**
 * The walkthrough as the landing's action when the live assistant is out of room: the same link,
 * in the tour button's look (a secondary button), so it takes the tour button's place.
 */
export function WalkthroughButton({ className }: { className?: string }) {
  const location = useLocation()
  return (
    <Link
      to={WALKTHROUGH_PATH}
      state={walkthroughState(location)}
      className={cn(buttonVariants({ variant: 'secondary' }), className)}
    >
      {WALKTHROUGH_LINK_TEXT}
    </Link>
  )
}
