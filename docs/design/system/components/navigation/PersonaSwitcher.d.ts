/** Sidebar footer control showing who you are exploring as. Name and title stay on one line each; a truncated title shows in full in a tooltip. Opens a shadcn DropdownMenu of the four sandbox personas. */
export interface PersonaSwitcherProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  name: string;
  title: string;
  /** Defaults to the first letters of the first two words of name. */
  initials?: string;
  onClick?: () => void;
  /** Specimens only: force the tooltip open (it still only shows when the title is truncated). */
  forceTooltip?: boolean;
  /** True while PersonaMenu is open; sets aria-expanded and the hover fill. */
  expanded?: boolean;
  /** While switching, e.g. "Switching to Marcus Bell…". Shows a spinner in place of the avatar and sets aria-busy. */
  busyLabel?: string;
}
export declare function PersonaSwitcher(props: PersonaSwitcherProps): JSX.Element;
