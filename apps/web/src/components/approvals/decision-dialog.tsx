import { useRef } from 'react'
import {
  AlertDialog,
  AlertDialogActions,
  AlertDialogCancel,
  AlertDialogConfirm,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { approvalsCopy, firstNameOf } from './labels'
import { NoteField } from './note-field'

type DecisionDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  kind: 'approve' | 'deny'
  person: { name: string }
  /** What the decision is about: "Monday, November 9 to Tuesday, November 10, 16 hours (2 days)." */
  facts: string
  /** The denial's note. Shown for `deny` only. */
  note: string
  onNoteChange: (note: string) => void
  /** True while the decision is being made: the button is busy, and Go back and the note lock. */
  deciding?: boolean
  onConfirm: () => void
  /**
   * Where focus goes when the dialog closes. A page that opens it from a button (not an
   * `AlertDialogTrigger`) calls `event.preventDefault()` and focuses that button.
   */
  onCloseAutoFocus?: (event: Event) => void
}

/**
 * Approve or deny one request (DecisionDialog.jsx) on the alert dialog. Both confirm with the
 * standard primary button, never a destructive one: Open Door favors neither decision. Approve
 * starts focus on "Go back"; deny starts it in the note. Escape goes back, except while deciding.
 * The page opens it from a button and puts focus back there when it closes.
 */
function DecisionDialog({
  open,
  onOpenChange,
  kind,
  person,
  facts,
  note,
  onNoteChange,
  deciding = false,
  onConfirm,
  onCloseAutoFocus,
}: DecisionDialogProps) {
  const noteRef = useRef<HTMLTextAreaElement>(null)
  const deny = kind === 'deny'
  const first = firstNameOf(person.name)
  const confirmLabel = deny
    ? deciding
      ? approvalsCopy.denying
      : approvalsCopy.deny
    : deciding
      ? approvalsCopy.approving
      : approvalsCopy.approve
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent
        busy={deciding}
        onCloseAutoFocus={onCloseAutoFocus}
        onOpenAutoFocus={
          deny
            ? (event) => {
                event.preventDefault()
                noteRef.current?.focus()
              }
            : undefined
        }
      >
        <AlertDialogTitle>{approvalsCopy.dialogTitle(kind, person.name)}</AlertDialogTitle>
        <AlertDialogDescription>
          {deny ? facts : `${facts} ${approvalsCopy.seeOnTimeOff(first)}`}
        </AlertDialogDescription>
        {deny && (
          <NoteField
            ref={noteRef}
            firstName={first}
            value={note}
            onChange={onNoteChange}
            disabled={deciding}
            className="mt-3"
          />
        )}
        <AlertDialogActions>
          <AlertDialogCancel>{approvalsCopy.goBack}</AlertDialogCancel>
          <AlertDialogConfirm
            loading={deciding}
            aria-disabled={deciding || undefined}
            onClick={onConfirm}
          >
            {confirmLabel}
          </AlertDialogConfirm>
        </AlertDialogActions>
      </AlertDialogContent>
    </AlertDialog>
  )
}

export { DecisionDialog }
export type { DecisionDialogProps }
