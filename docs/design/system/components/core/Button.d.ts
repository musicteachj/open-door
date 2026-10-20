import type { IconName } from './Icon';

/**
 * Open Door button. Variants map to shadcn Button: primary = default, secondary = outline, ghost = ghost, destructive = destructive.
 * Pass data-state="hover" or "focus" to render a state statically in specimens.
 */
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'destructive';
  /** md is 40 px tall (default); sm is 32 px, for inline actions like Retry. */
  size?: 'md' | 'sm';
  /** Leading Lucide icon. */
  icon?: IconName;
  /** Trailing Lucide icon, e.g. arrow-right on Ask. */
  iconRight?: IconName;
  /** Submitting: swaps the leading icon for a spinning loader-circle, sets aria-busy and aria-disabled, and ignores clicks. Keep the label as a present participle, e.g. "Requesting…". */
  loading?: boolean;
  children?: React.ReactNode;
}
export declare function Button(props: ButtonProps): JSX.Element;
