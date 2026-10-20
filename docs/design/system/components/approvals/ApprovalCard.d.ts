/** One PTO request waiting for the manager. Head: avatar, name, title, and "Sent October 17" (or a Canceled badge in conflict). Body: dates, "PTO · amount", "available after this", and Team coverage; Approve and Deny on the right, both secondary and the same size, Approve first: Open Door never favors either decision. Facts only: never a score, warning color, ranking, or suggestion. conflict mutes the card, swaps the actions for a refusal message (role="alert"). Maps to shadcn Card. */
export interface ApprovalCardProps {
  person: { name: string; title: string; initials: string };
  /** "Monday, November 9 to Tuesday, November 10" */
  dates: string;
  /** For the buttons' accessible names: "November 9 to 10" gives "Approve Zara Bautista's PTO, November 9 to 10". */
  shortDates: string;
  /** "16 hours (2 days)" */
  amount: string;
  /** "62 hours (7.75 days) available after this": the person's available figure as it stands, since a waiting request already counts against it. */
  availableAfter: string;
  /** "Sent October 17" or "Sent today" */
  sent: string;
  /** One line per overlap ("Also off: Vikram Morales, Tuesday, November 10 · PTO"), or the single no-overlap line. */
  coverage: string[];
  /** The refusal text when the request changed underneath, e.g. "Zara canceled this request." */
  conflict?: string;
  onApprove?: () => void;
  onDeny?: () => void;
  loading?: boolean;
  /** Specimen states for the buttons. 'loading' shows "Approving…". */
  approveState?: 'hover' | 'focus' | 'loading' | 'disabled';
  denyState?: 'hover' | 'focus' | 'disabled';
}
export declare function ApprovalCard(props: ApprovalCardProps): JSX.Element;
