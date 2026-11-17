import type { Ref } from 'react'
import { TurnstileSlot } from '@/components/landing/turnstile-slot'
import {
  AlertDialog,
  AlertDialogActions,
  AlertDialogCancel,
  AlertDialogConfirm,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

type TourStartDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** "Start the tour". The caller closes the dialog when the new sandbox has started. */
  onStart: () => void
  /** The new sandbox is starting: the button shows it is busy and ignores presses. */
  starting?: boolean
  /** Something else is changing who the visitor is (a persona switch): "Start the tour" waits. */
  blocked?: boolean
  /** The empty place under the buttons for Cloudflare's check, which only shows when it asks. */
  slotRef?: Ref<HTMLDivElement>
}

/**
 * "Start the tour?" from the persona menu (from `TourStartDialog`): the app's own alert dialog on
 * its normal scrim, 480 px wide. Cancel takes focus first and Escape cancels. On a phone the
 * dialog keeps the overlay's 16 px margins and the buttons stack at full width, the primary on top
 * with Cancel still first in the tab order (all `AlertDialog`'s own behavior).
 */
function TourStartDialog({
  open,
  onOpenChange,
  onStart,
  starting = false,
  blocked = false,
  slotRef,
}: TourStartDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent busy={starting}>
        <AlertDialogTitle>Start the tour?</AlertDialogTitle>
        <AlertDialogDescription>
          The tour starts a new sandbox as Priya Raman. Your current sandbox stays until it expires.
        </AlertDialogDescription>
        <AlertDialogActions>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogConfirm loading={starting} disabled={blocked} onClick={onStart}>
            Start the tour
          </AlertDialogConfirm>
        </AlertDialogActions>
        <TurnstileSlot ref={slotRef} />
      </AlertDialogContent>
    </AlertDialog>
  )
}

export { TourStartDialog }
export type { TourStartDialogProps }
