import type { IconName } from '../core/Icon';

/** Sidebar link. Current page uses the primary tint; hover is neutral gray so it never reads as selected. Wrap a list in <nav className="od-nav">. */
export interface NavItemProps extends React.AnchorHTMLAttributes<HTMLAnchorElement> {
  icon?: IconName;
  label: string;
  href?: string;
  /** Marks the current page (aria-current="page"). */
  current?: boolean;
  /** Waiting items, e.g. requests for Approvals. Hidden when 0. */
  count?: number;
  /** Read after the count by screen readers. Default "waiting". */
  countLabel?: string;
}
export declare function NavItem(props: NavItemProps): JSX.Element;
