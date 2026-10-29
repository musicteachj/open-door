import {
  AlertDialog,
  AlertDialogActions,
  AlertDialogCancel,
  AlertDialogConfirm,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { detailCopy } from './labels'

type CaseStatusDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** `review` is "Start review of this case?"; `close` is "Close this case?". */
  kind: 'review' | 'close'
  /** The person's given name: they will see the new status in My cases. */
  firstName: string
  /** The change is in flight: the primary is busy, and Cancel and Escape do nothing. */
  pending?: boolean
  onConfirm: () => void
  /**
   * Where focus goes when the dialog closes. The page opens it from a button, so it calls
   * `event.preventDefault()` and focuses that button, or the next one after a confirm
   * ("Start review" moves it to "Close case"; "Close case" moves it to the heading).
   */
  onCloseAutoFocus?: (event: Event) => void
}

/**
 * Confirm a status change (screen 12's dialogs) on the 480 px alert dialog: focus starts on Cancel,
 * Escape and Cancel close it. Both confirm with the standard primary button, never a destructive
 * one: closing a case is not a warning. The person's name appears as the first name only.
 */
function CaseStatusDialog({
  open,
  onOpenChange,
  kind,
  firstName,
  pending = false,
  onConfirm,
  onCloseAutoFocus,
}: CaseStatusDialogProps) {
  const review = kind === 'review'
  const confirmLabel = review
    ? pending
      ? detailCopy.starting
      : detailCopy.startReview
    : pending
      ? detailCopy.closing
      : detailCopy.closeCase
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent busy={pending} onCloseAutoFocus={onCloseAutoFocus}>
        <AlertDialogTitle>
          {review ? detailCopy.reviewTitle : detailCopy.closeTitle}
        </AlertDialogTitle>
        <AlertDialogDescription>
          {review ? detailCopy.reviewBody(firstName) : detailCopy.closeBody(firstName)}
        </AlertDialogDescription>
        <AlertDialogActions>
          <AlertDialogCancel>{detailCopy.cancel}</AlertDialogCancel>
          <AlertDialogConfirm
            loading={pending}
            aria-disabled={pending || undefined}
            onClick={onConfirm}
          >
            {confirmLabel}
          </AlertDialogConfirm>
        </AlertDialogActions>
      </AlertDialogContent>
    </AlertDialog>
  )
}

export { CaseStatusDialog }
export type { CaseStatusDialogProps }
