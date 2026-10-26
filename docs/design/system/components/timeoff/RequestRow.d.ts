/** One time-off request in My requests: dates (600) over "type · amount", a StatusBadge with who decided under it, and Cancel where allowed (pending any time; approved or recorded until the first day). A manager's note on a denial sits below in a sunken box. Rows aren't links. RequestGroup wraps rows under an "Upcoming" or "Past" heading, with an optional empty line. Below 640 px the status drops under the dates and Cancel stays top right. */
export interface RequestRowProps {
  type?: 'pto' | 'sick';
  dates?: string;
  amount?: string;
  status?: 'waiting' | 'approved' | 'denied' | 'recorded' | 'canceled';
  decidedBy?: string;
  note?: string;
  canCancel?: boolean;
  onCancel?: () => void;
  loading?: boolean;
  cancelState?: 'hover' | 'focus';
  /** Row tint on hover and while anything inside has focus; force it for specimens. */
  'data-state'?: 'hover' | 'focus';
  /** Team view (Approvals): adds an avatar and name column and drops the Cancel column. */
  person?: { name: string; initials: string };
  /** Overrides the "Approved by …" line, e.g. "Approved October 5" or "Denied today" on the manager's Recent decisions. */
  decidedLine?: string;
  /** Overrides the note label, e.g. "Your note" when the viewer wrote it. */
  noteLabel?: string;
}
export declare function RequestRow(props: RequestRowProps): JSX.Element;
export interface RequestGroupProps { title: string; empty?: string; children?: React.ReactNode; }
export declare function RequestGroup(props: RequestGroupProps): JSX.Element;
