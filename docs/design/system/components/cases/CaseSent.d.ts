/** The quiet sent line (role="status", focus target) or the five-waiting limit. */
export interface CaseSentProps {
  variant?: 'sent' | 'limit';
  replyBy?: string;
  /** false on My cases, where the row is already on the page. */
  showLink?: boolean;
  href?: string;
}
export declare function CaseSent(props: CaseSentProps): JSX.Element;
