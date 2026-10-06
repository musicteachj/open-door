/** Titled, bordered group of DetailRow items on a profile ("Work details", "Private details"). Optional note after the title and an audit note above the rows. */
export interface DetailListProps {
  title: string;
  icon?: 'lock' | string;
  /** e.g. "Only you and HR can see these." */
  note?: string;
  /** Shown whenever private values are visible; every read is audited, including your own. */
  auditNote?: string;
  children: React.ReactNode;
}
export declare function DetailList(props: DetailListProps): JSX.Element;
