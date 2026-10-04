import type { IconName } from '../core/Icon';

/** On/off filter such as "My team". Pressed fills with the tint and swaps the icon for a check. Maps to shadcn Toggle. */
export interface FilterToggleProps {
  label: string;
  icon?: IconName;
  count?: number;
  pressed?: boolean;
  onChange?: (pressed: boolean) => void;
  className?: string;
  /** Specimens only: data-state="hover" | "focus". */
  'data-state'?: string;
}
export declare function FilterToggle(props: FilterToggleProps): JSX.Element;
