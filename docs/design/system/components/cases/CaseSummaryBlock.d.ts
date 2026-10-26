/** The AI summary of a case, labeled as the AI's. */
export interface CaseSummaryBlockProps {
  id?: string;
  state?: 'ready' | 'pending' | 'failed' | 'crisis';
  text?: string;
  /** "Mon, Oct 26, 10:41 AM MDT" in the reader's zone */
  writtenAt?: string;
  model?: string;
  onRetry?: () => void;
}
export declare function CaseSummaryBlock(props: CaseSummaryBlockProps): JSX.Element;
