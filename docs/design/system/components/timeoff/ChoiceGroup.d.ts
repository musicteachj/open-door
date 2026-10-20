/** Labeled radio cards, two per row, 44 px minimum. Selected: primary border (2 px effective), primary tint, filled radio dot. Arrow keys move and select. Maps to shadcn RadioGroup with card items. */
export interface ChoiceOption { value: string; label: string; state?: string; }
export interface ChoiceGroupProps {
  id?: string;
  label?: string;
  options: ChoiceOption[];
  value: string;
  onChange?: (value: string) => void;
  disabled?: boolean;
}
export declare function ChoiceGroup(props: ChoiceGroupProps): JSX.Element;
