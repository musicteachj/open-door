/** Categories, in order: Harassment or discrimination; Workplace safety; Medical or accommodation; Pay concern; Something else, or not sure. */
/** The confidential-case form. Opens in place (never a modal) in the HR panel's band or a card on My cases. */
export interface CaseFormProps {
  id?: string;
  /** 3 inside the HR panel (under its h2), 2 on My cases (under the h1). */
  headingLevel?: 2 | 3;
  /** 'error' = the send failed; category and words are kept and the primary reads "Try again". */
  state?: 'form' | 'sending' | 'error';
  category?: string | null;
  /** Prefilled from the message that raised the panel; empty on My cases. */
  words?: string;
  /** The flagged message was a short reply: the hint becomes "Add what happened…". */
  short?: boolean;
  /** Two business days from today, written out: "Wednesday, October 28". */
  replyBy?: string;
  errors?: { category?: string; words?: string; limit?: boolean };
  onCategory?: (value: string) => void;
  onWords?: (value: string) => void;
  onSend?: () => void;
  onClose?: () => void;
  sendState?: 'hover' | 'focus';
  max?: number;
}
export declare function CaseForm(props: CaseFormProps): JSX.Element;
