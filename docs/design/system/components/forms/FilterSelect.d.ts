export interface FilterOption { value: string; label: string; count?: number; }

/** Single-choice filter: a trigger reading "Label Value" and a menu of options with counts and a check on the selected one. An active filter fills with the primary tint. Maps to a shadcn Select or Popover with Command. */
export interface FilterSelectProps {
  label: string;
  /** null means All. */
  value?: string | null;
  options: FilterOption[];
  /** First menu item, e.g. "All locations". */
  allLabel?: string;
  onChange?: (value: string | null) => void;
  /** Specimens only. */
  defaultOpen?: boolean;
  className?: string;
  /** Specimens only: data-state="hover" | "focus". */
  'data-state'?: string;
}
export declare function FilterSelect(props: FilterSelectProps): JSX.Element;
