/** The person's words behind a recorded reveal. Starts hidden on every view. */
export interface CaseWordsRevealProps {
  id?: string;
  firstName: string;
  words: string;
  open?: boolean;
  /** Record the read on the server before showing; the timeline gains "Dana Whitfield read Priya's words". */
  onToggle?: () => void;
  buttonState?: 'hover' | 'focus';
}
export declare function CaseWordsReveal(props: CaseWordsRevealProps): JSX.Element;
