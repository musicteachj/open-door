export type IconName = 'message-circle' | 'calendar' | 'users' | 'book-open' | 'code' | 'clock' | 'info' | 'circle-alert' | 'rotate-ccw' | 'chevrons-up-down' | 'chevron-right' | 'arrow-right' | 'arrow-up' | 'trash-2';

/** Lucide icon at Open Door's stroke weight (1.75). Decorative unless a label is given. */
export interface IconProps {
  name: IconName;
  /** Pixel size. 18 in nav, 16 in buttons and rows, 14 inline with small text. */
  size?: number;
  strokeWidth?: number;
  /** Accessible name. Omit for decorative icons next to text. */
  label?: string;
  className?: string;
  style?: React.CSSProperties;
}
export declare function Icon(props: IconProps): JSX.Element;
