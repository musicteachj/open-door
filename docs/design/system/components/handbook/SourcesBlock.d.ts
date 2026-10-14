/** Small block, headed "Sources", under an addendum section's body listing where each statutory figure was checked. One line per source, with no "Source:" prefix. */
export interface SourcesBlockProps {
  /** e.g. "California Labor Code §246, read from dir.ca.gov on Oct 6, 2026." */
  sources: string[];
  className?: string;
}
export declare function SourcesBlock(props: SourcesBlockProps): JSX.Element;
