export interface CaseQueueRow {
  href: string; initials: string; name: string; title: string; location: string; category: string;
  /** Neutral fact under the category when the safety check routed the message to crisis text. Never a warning. */
  crisisFact?: boolean;
  sent: string;
  /** "Reply due today", "Reply was due Mon, Oct 26", "Reply due Tue, Oct 27", "In review since Tue, Oct 20", "Closed Fri, Oct 16". Neutral ink, never a warning color. */
  reply: string;
  status: 'case-new' | 'case-in-review' | 'case-closed';
  state?: 'hover' | 'focus';
}
/** HR queue. Rows are links in reading order. No words, no summary, no ranking; sorted by reply date only (server). */
export declare function CaseQueueTable(props: { rows: CaseQueueRow[]; emptyText?: string }): JSX.Element;
