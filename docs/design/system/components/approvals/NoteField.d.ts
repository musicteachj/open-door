/** Optional note on a denial. Label above, 4-row textarea, helper on the left and "0 of 300" on the right, both in its description. Hard limit via maxLength; screen readers hear "N characters left" only in the last 20. Same border, hover, and focus halo as the composer and hours stepper. Maps to shadcn Textarea + Label. */
export interface NoteFieldProps {
  id?: string;
  label: string;
  helper: string;
  value?: string;
  max?: number;
  disabled?: boolean;
  onChange?: (value: string) => void;
  'data-state'?: 'hover' | 'focus';
}
export declare function NoteField(props: NoteFieldProps): JSX.Element;
