/** "Last updated Sep 12, 2026" in 13 px ink-muted with tabular figures. bare renders only the date (section list column). */
export interface LastUpdatedProps {
  /** Formatted like "Sep 12, 2026". */
  date: string;
  bare?: boolean;
  className?: string;
}
export declare function LastUpdated(props: LastUpdatedProps): JSX.Element;
