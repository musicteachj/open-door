/** Bordered block of links between company sections and state addenda. "State rules" on a company section lists its addenda (with the yes marker where one applies). "Supplements" on an addendum links back to the company section. */
export interface LinkBlockLink { label: string; meta?: string; href: string; appliesToYou?: boolean; onOpen?: () => void; 'data-state'?: string; }
export interface LinkBlockProps {
  title: 'State rules' | 'Supplements' | string;
  note?: string;
  links: LinkBlockLink[];
  className?: string;
}
export declare function LinkBlock(props: LinkBlockProps): JSX.Element;
