/**
 * Centered page-level message for expired sessions, not found, and server errors: a 28 px title, one plain sentence, an optional mono reference, and one action. No illustration.
 * @startingPoint section="States" subtitle="Full-page message for expired, not found, and error" viewport="700x360"
 */
export interface FullPageMessageProps {
  title: string;
  body?: string;
  /** Short request ID shown in mono, selectable with one click. */
  reference?: string;
  /** Actions: one Button or a text link. */
  children?: React.ReactNode;
  className?: string;
}
export declare function FullPageMessage(props: FullPageMessageProps): JSX.Element;
