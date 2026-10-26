/** A proposed time-off action, shown under the assistant's one-line reply. The AI proposes; nothing happens until the person presses Confirm. Every figure comes from the time-off engine, never from the model's text.
 * Header: action name ("Book PTO", "Record sick time", "Approve a request", "Deny a request", "Cancel time off") and a status slot: "Expires at 3:42 PM" while pending, the StatusBadge once executed.
 * Body: who (decisions, with Avatar), facts list, PreviewBlock for bookings ("What this uses" with its sources), team coverage for decisions, an info line, the short-notice FormMessage, NoteField for deny, source chips.
 * Footer while pending: "Proposed by the AI. Nothing happens until you confirm.", Confirm (primary on every variant, deny included) and Dismiss (secondary). The secondary button is never called Cancel, so it can't be mistaken for the "Cancel time off" action.
 * Final states replace the footer: executed (apricot line, role="status", focus moves here, with "View in Time off" or, for decisions, "View in Approvals"), failed (refusal, role="alert", facts muted), dismissed ("You dismissed this. Nothing was changed."), replaced, expired (neutral, facts muted; expired adds "Ask again"). Buttons never come back.
 * Maps to shadcn Card + Button. */
export interface ConfirmCardProps {
  id?: string;
  title: string;
  icon?: 'calendar-plus' | 'calendar-x' | 'clipboard-check';
  state?: 'pending' | 'streaming' | 'confirming' | 'executed' | 'failed' | 'dismissed' | 'replaced' | 'expired';
  /** "Expires at 3:42 PM". Never a ticking countdown. */
  expires?: string;
  who?: { name: string; title: string; initials: string };
  /** Short list. value or badge (e.g. the current "Approved" on a cancellation). */
  facts?: { label: string; value?: string; badge?: 'approved' | 'waiting' | 'recorded' }[];
  /** PreviewBlock props without sources; sources are passed separately and rendered inside it. */
  preview?: { counted: { label: string; hours: string }[]; skipped?: string[]; amount: string; left: string };
  coverage?: string;
  info?: string;
  /** Screen 08's amber short-notice message. Pending only. */
  warning?: string;
  /** Deny only: the note and its handler. The field shows while pending; the note shows as "Your note" once executed. */
  note?: string;
  onNoteChange?: (v: string) => void;
  sources?: { label: string; href: string }[];
  /** "Confirm", or "Deny" on a deny card. Always the primary button. */
  confirmLabel?: string;
  /** "Confirm: book PTO on Friday, October 30" */
  confirmAria?: string;
  /** "Dismiss, don't book PTO on Friday, October 30"; on a cancellation, "Dismiss, keep PTO on Wednesday, December 23" */
  dismissAria?: string;
  onConfirm?: () => void;
  onDismiss?: () => void;
  onAskAgain?: () => void;
  executedText?: string;
  /** "View in Time off" (/time-off), or "View in Approvals" (/approvals) on approve and deny cards. */
  executedLink?: { label: string; href: string };
  badge?: 'waiting' | 'approved' | 'denied' | 'recorded' | 'canceled';
  failedText?: string;
  confirmState?: 'hover' | 'focus';
  dismissState?: 'hover' | 'focus';
}
export declare function ConfirmCard(props: ConfirmCardProps): JSX.Element;
