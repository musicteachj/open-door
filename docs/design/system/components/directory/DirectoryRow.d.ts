/** One person in the directory list: avatar initials, name (with a "You" tag on your own row), title, department, location. The whole row links to the profile; tint on hover, inset ring on focus. Stacks under 760 px. */
export interface DirectoryRowProps {
  name: string;
  initials?: string;
  title: string;
  department: string;
  location: string;
  /** Profile URL. */
  href?: string;
  isYou?: boolean;
  /** Client-side navigation; prevents the default link. */
  onOpen?: () => void;
  className?: string;
  /** Specimens only: data-state="hover" | "focus". */
  'data-state'?: string;
}
export declare function DirectoryRow(props: DirectoryRowProps): JSX.Element;
