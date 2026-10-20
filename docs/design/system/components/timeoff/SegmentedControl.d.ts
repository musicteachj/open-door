/** Labeled two-option (or few-option) single choice, a radiogroup of buttons. Selected: primary tint, ink 600, check icon, so color is never the only signal. Arrow keys move and select; one tab stop. Maps to shadcn ToggleGroup type="single" (or RadioGroup). Pass option.state = "hover" | "focus" | "active" for specimens. */
export interface SegmentedOption { value: string; label: string; state?: string; }
export interface SegmentedControlProps {
  id?: string;
  label: string;
  options: SegmentedOption[];
  value: string;
  onChange?: (value: string) => void;
  disabled?: boolean;
}
export declare function SegmentedControl(props: SegmentedControlProps): JSX.Element;
