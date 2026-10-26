import type { RequestOut } from '@/api/generated'
import {
  AlertDialog,
  AlertDialogActions,
  AlertDialogCancel,
  AlertDialogConfirm,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { cancelCopy, cancelDescription, cancelTitle } from '@/components/timeoff/labels'

type CancelRequestDialogProps = {
  /** The request being canceled, or null while the dialog is closed. */
  request: RequestOut | null
  onOpenChange: (open: boolean) => void
  /** True while the cancel is running: the button is busy, and Keep it and Escape wait. */
  canceling?: boolean
  onConfirm: () => void
  /** Where focus goes when the dialog closes; the page decides, since it knows why it closed. */
  onCloseAutoFocus: (event: Event) => void
}

/**
 * The one confirm step before a request is canceled (docs/design/screens/08-time-off), on the
 * alert dialog: focus starts on "Keep it", the safe choice, and the confirm is the standard
 * primary button. The facts come from the request's own API label.
 */
function CancelRequestDialog({
  request,
  onOpenChange,
  canceling = false,
  onConfirm,
  onCloseAutoFocus,
}: CancelRequestDialogProps) {
  return (
    <AlertDialog open={request !== null} onOpenChange={onOpenChange}>
      <AlertDialogContent busy={canceling} onCloseAutoFocus={onCloseAutoFocus}>
        {request && (
          <>
            <AlertDialogTitle>{cancelTitle(request.startDate, request.endDate)}</AlertDialogTitle>
            <AlertDialogDescription>
              {cancelDescription(request.amountLabel)}
            </AlertDialogDescription>
          </>
        )}
        <AlertDialogActions>
          <AlertDialogCancel>{cancelCopy.keepIt}</AlertDialogCancel>
          <AlertDialogConfirm
            loading={canceling}
            aria-disabled={canceling || undefined}
            onClick={onConfirm}
          >
            {canceling ? cancelCopy.canceling : cancelCopy.cancelRequest}
          </AlertDialogConfirm>
        </AlertDialogActions>
      </AlertDialogContent>
    </AlertDialog>
  )
}

export { CancelRequestDialog }
export type { CancelRequestDialogProps }
