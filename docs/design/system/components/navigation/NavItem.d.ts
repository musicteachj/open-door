import type { IconName } from '../core/Icon';

/** Sidebar link. Current page uses the primary tint; hover is neutral gray so it never reads as selected. Wrap a list in <nav className="od-nav">. */
export interface NavItemProps extends React.AnchorHTMLAttributes<HTMLAnchorElement> {
  icon?: IconName;
  label: string;
  href?: string;
  /** Marks the current page (aria-current="page"). */
  current?: boolean;
}
export declare function NavItem(props: NavItemProps): JSX.Element;
