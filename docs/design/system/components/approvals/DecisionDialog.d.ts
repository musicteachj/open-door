/** The confirm step for approving or denying a PTO request: screen 08's alert dialog (centered, 480 px, full-window scrim). Title "Approve Zara Bautista's PTO?", the facts, and for deny an optional NoteField. Buttons: Go back (secondary), then the confirm button, always the standard primary: "Approve" or "Deny". Never destructive: a denial is a decision, not an error. The body never uses a pronoun: "Zara will see it on the Time off page." phase 'deciding' shows "Approving…" or "Denying…" and disables Go back and the note. Focus: Go back for approve, the note for deny; Tab is trapped; Escape goes back unless deciding. No AI label: this is the manager's own action. Maps to shadcn AlertDialog. */
export interface DecisionDialogProps {
  id?: string;
  kind: 'approve' | 'deny';
  person: { name: string; first: string };
  /** "Monday, November 9 to Tuesday, November 10, 16 hours (2 days)." */
  facts: string;
  note?: string;
  onNoteChange?: (v: string) => void;
  phase?: null | 'deciding';
  onConfirm?: () => void;
  onBack?: () => void;
  /** false renders the dialog inline, for specimens. */
  scrim?: boolean;
  backState?: 'hover' | 'focus';
  noteState?: 'hover' | 'focus';
}
export declare function DecisionDialog(props: DecisionDialogProps): JSX.Element;
