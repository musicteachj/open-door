/** One handbook section in the table of contents: number, title, Applies to value, the "Applies to you" marker only when the section has a restricted audience (a state, an employment type, or a location) that covers the person (rows for Everyone stay unmarked), the last-updated date, and a chevron. The whole row links to the section. Hover: primary tint. Focus: inset ring. Current: tint, 600 title, aria-current="page". Rows are plain links in the Tab order with the visible focus ring, as in the directory; no arrow-key handling. Stacks under 760 px. */
export interface SectionRowProps {
  /** "4.3" or "CA-4.3". */
  num: string;
  title: string;
  /** Built with appliesLabel(). */
  applies?: string;
  appliesToYou?: boolean;
  /** "Aug 3, 2026". */
  updated: string;
  href?: string;
  current?: boolean;
  onOpen?: () => void;
  className?: string;
  /** Specimens only: "hover" | "focus" | "current". */
  'data-state'?: string;
}
export declare function SectionRow(props: SectionRowProps): JSX.Element;
export interface SectionGroupProps { num: string; title: string; note?: string; id: string; children?: React.ReactNode; }
export declare function SectionGroup(props: SectionGroupProps): JSX.Element;
