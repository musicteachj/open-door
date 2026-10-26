/** Trigger for the date picker. Looks like a 44 px text field with a calendar icon and a chevron; shows the chosen day or range in words, or a placeholder. aria-expanded drives the open style (primary border plus focus halo). The picker opens inline below it (shadcn Collapsible + Calendar) rather than in a popover, so it never covers the live preview. */
export interface DateFieldProps {
  id?: string;
  label?: string;
  /** Short form shown in the field: "Mon, Nov 2 to Thu, Nov 5". */
  value?: string;
  /** Full form for the accessible name: "Monday, November 2 to Thursday, November 5". */
  fullValue?: string;
  placeholder?: string;
  open?: boolean;
  /** id of the DatePicker it opens. */
  controls?: string;
  error?: string | null;
  disabled?: boolean;
  onToggle?: () => void;
  'data-state'?: 'hover' | 'focus';
}
export declare function DateField(props: DateFieldProps): JSX.Element;
