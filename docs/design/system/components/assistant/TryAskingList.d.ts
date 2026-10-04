/** Labeled two-column list of suggested questions; collapses to one column under 640 px. */
export interface TryAskingListProps {
  label?: string;
  questions: string[];
  onSelect?: (question: string) => void;
  className?: string;
}
export declare function TryAskingList(props: TryAskingListProps): JSX.Element;
