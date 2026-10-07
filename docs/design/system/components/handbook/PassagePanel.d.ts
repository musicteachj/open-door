/**
 * Shows one cited passage beside the content without leaving the page. Shared by the handbook and the assistant's source panel.
 * Header (eyebrow matching the section page: "Handbook CA-4.3 · California addendum" for addenda, no §; "Handbook §4.3 · Time off" for company sections; title, badge, marker, last updated, close) and footer ("Open in handbook") stay fixed; the body scrolls, so any passage length fits.
 * The cited paragraph uses CitedPassage (compact), with the paragraphs before and after in ink-muted for context.
 * Docked on the right at 420 px, full height, with a left border; not modal; on the assistant home it takes the rail's place while open. On open, focus moves to the title; Escape or close returns focus to the citation that opened it. Errors are inline, never a toast; "Open in handbook" stays available.
 * @startingPoint section="Handbook" subtitle="Cited passage beside content: open, loading, error" viewport="420x640"
 */
export interface PassagePanelProps {
  state?: 'open' | 'loading' | 'error';
  /** "Handbook CA-4.3 · California addendum" or "Handbook §4.3 · Time off". */
  eyebrow: string;
  title?: string;
  applies?: string;
  /** Omit to hide the marker. */
  appliesToYou?: boolean;
  updated?: string;
  before?: string;
  cited?: string;
  after?: string;
  /** Deep link: /handbook/CA-4.3?passage=p2 */
  href: string;
  onClose?: () => void;
  onOpen?: () => void;
  onRetry?: () => void;
  className?: string;
}
export declare function PassagePanel(props: PassagePanelProps): JSX.Element;
