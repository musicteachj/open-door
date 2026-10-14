/** One handbook search result: number, title and group, a one-line excerpt with the matched words in a <mark> (tint plus 600 weight), then the badge, marker (yes or no), and last-updated date. Results the person is covered by sort first. */
export interface SearchResultRowProps {
  num: string;
  title: string;
  /** "Company handbook" or "California addendum". */
  group?: string;
  excerpt?: string;
  /** The query, emphasized inside the excerpt. */
  match?: string;
  applies: string;
  appliesToYou: boolean;
  updated: string;
  href?: string;
  onOpen?: () => void;
  className?: string;
  'data-state'?: string;
}
export declare function SearchResultRow(props: SearchResultRowProps): JSX.Element;
