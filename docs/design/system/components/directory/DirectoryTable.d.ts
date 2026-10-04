export interface DirectoryPerson { id: string; name: string; title: string; department: string; location: string; href?: string; }

/**
 * The directory list: column header, rows, loading skeleton, empty result, and a "Show more" button that reveals 50 more (no page numbers).
 * @startingPoint section="Directory" subtitle="People list with loading, empty, and Show more" viewport="700x520"
 */
export interface DirectoryTableProps {
  /** Already filtered and sorted. */
  people: DirectoryPerson[];
  /** Count shown in "Showing 50 of N"; defaults to people.length. */
  total?: number;
  loading?: boolean;
  /** How many rows are revealed. Start at 50. */
  shown?: number;
  onShowMore?: () => void;
  onOpen?: (person: DirectoryPerson) => void;
  /** The viewer's id, to tag their row "You". */
  youId?: string;
  /** Current search text, used in the empty message. */
  query?: string;
  onClear?: () => void;
  clearLabel?: string;
}
export declare function DirectoryTable(props: DirectoryTableProps): JSX.Element;
