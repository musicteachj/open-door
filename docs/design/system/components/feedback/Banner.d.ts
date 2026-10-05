/** Full-width notice across the top of the content sheet. Neutral sunken background; only the icon carries the tone color, the text stays ink. Dismissible for the session. Maps to shadcn Alert. */
export interface BannerProps {
  message: string;
  tone?: 'warning' | 'info';
  /** Omit to make it non-dismissible. */
  onDismiss?: () => void;
  dismissLabel?: string;
  className?: string;
}
export declare function Banner(props: BannerProps): JSX.Element;
