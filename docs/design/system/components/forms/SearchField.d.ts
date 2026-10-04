/** Search input with a leading search icon, input-border (3:1+), focus halo, and a clear button once there is text. Escape clears. Maps to a shadcn Input. */
export interface SearchFieldProps {
  value: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  /** Accessible name; say what is searched. */
  label?: string;
  className?: string;
  /** Specimens only: data-state="hover" | "focus". */
  'data-state'?: string;
}
export declare function SearchField(props: SearchFieldProps): JSX.Element;
