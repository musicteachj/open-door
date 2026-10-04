/** At-a-glance figure that links to the page holding the detail. Names its destination; tint on hover with underlined destination; ring on focus. */
export interface GlanceLinkProps extends React.AnchorHTMLAttributes<HTMLAnchorElement> {
  /** The figure, e.g. "11.5" or "Sep 12". Rendered with tabular figures. */
  value: string;
  caption: string;
  /** Page name shown with a chevron, e.g. "Time off". */
  destination: string;
  href?: string;
  /** Cinnamon marker dot for something that needs a look (a pending request). Decorative; the caption carries the meaning. */
  marker?: boolean;
}
export declare function GlanceLink(props: GlanceLinkProps): JSX.Element;
