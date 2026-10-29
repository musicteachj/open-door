import { Info } from 'lucide-react'
import { useId, type Ref } from 'react'
import type { Status } from '@/api/generated'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { detailCopy } from './labels'

type CaseStatusActionsProps = {
  status: Status
  firstName: string
  /** The words have not been read on this case yet, by this person: nothing can change. */
  locked: boolean
  onStartReview: () => void
  onClose: () => void
  /** The page moves focus here after "Start review" is confirmed. */
  closeButtonRef?: Ref<HTMLButtonElement>
  /** And reads this to return focus to the button that opened a dialog. */
  startButtonRef?: Ref<HTMLButtonElement>
  className?: string
}

// A locked button looks disabled but stays in the tab order and says why (`aria-describedby`).
// The hover is forced back, because the base variants only gate theirs on `:enabled`.
const LOCKED =
  'aria-disabled:cursor-not-allowed aria-disabled:border-disabled-bg aria-disabled:bg-disabled-bg aria-disabled:text-disabled-fg aria-disabled:hover:border-disabled-bg! aria-disabled:hover:bg-disabled-bg!'
const LOCKED_SECONDARY = 'aria-disabled:bg-surface-raised aria-disabled:hover:bg-surface-raised!'

/**
 * The status changes HR can make: Start review and Close case on a new case, Close case in review,
 * nothing once closed. Until HR has read the words on this case the buttons are `aria-disabled`
 * and still focusable, described by the read-first line, and do nothing when pressed. The server
 * refuses an early change too. The page opens the confirm dialog from `onStartReview` and `onClose`.
 */
function CaseStatusActions({
  status,
  firstName,
  locked,
  onStartReview,
  onClose,
  closeButtonRef,
  startButtonRef,
  className,
}: CaseStatusActionsProps) {
  const lineId = useId()
  if (status === 'closed') {
    return (
      <p data-slot="case-status-actions" className={cn('m-0 text-ui text-ink-muted', className)}>
        {detailCopy.caseClosed}
      </p>
    )
  }
  const lock = locked ? { 'aria-disabled': true as const, 'aria-describedby': lineId } : undefined
  return (
    <div data-slot="case-status-actions" className={cn('flex flex-col gap-3', className)}>
      <fieldset
        aria-label={detailCopy.changeStatus}
        className="m-0 flex min-w-0 flex-wrap gap-3 border-0 p-0 max-sm:flex-col"
      >
        {status === 'new' && (
          <Button
            ref={startButtonRef}
            {...lock}
            onClick={locked ? undefined : onStartReview}
            className={cn(LOCKED, 'max-sm:w-full')}
          >
            {detailCopy.startReview}
          </Button>
        )}
        <Button
          ref={closeButtonRef}
          variant="secondary"
          {...lock}
          onClick={locked ? undefined : onClose}
          className={cn(LOCKED, LOCKED_SECONDARY, 'max-sm:w-full')}
        >
          {detailCopy.closeCase}
        </Button>
      </fieldset>
      {locked && (
        <p id={lineId} className="m-0 flex items-center gap-2 text-ui font-regular text-ink-muted">
          <Info aria-hidden="true" className="size-3.5 flex-none" />
          {detailCopy.readFirst(firstName)}
        </p>
      )}
    </div>
  )
}

export { CaseStatusActions }
export type { CaseStatusActionsProps }
