/** Labeled whole-number input with minus and plus buttons, 44 px tall. The buttons disable at min and max. Typing is allowed; the parent validates and passes error. Hint sits beside it; the error sits below with role="alert". Maps to a shadcn Input inside a button group. */
export interface HoursStepperProps {
  id?: string;
  label?: string;
  /** String so a typed value can be invalid while the person edits. */
  value: string;
  min?: number;
  max?: number;
  hint?: string;
  error?: string | null;
  disabled?: boolean;
  onChange?: (value: string) => void;
  'data-state'?: 'hover' | 'focus';
}
export declare function HoursStepper(props: HoursStepperProps): JSX.Element;
