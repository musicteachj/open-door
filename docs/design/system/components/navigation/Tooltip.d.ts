/** Small ink tooltip on hover or focus; Escape dismisses it. Maps to shadcn Tooltip. */
export interface TooltipProps {
  content: React.ReactNode;
  /** Force open or closed. Leave undefined to follow hover and focus. */
  open?: boolean;
  /** Suppress the tooltip, e.g. when the text it repeats is fully visible. */
  disabled?: boolean;
  className?: string;
  /** A single focusable element. It receives aria-describedby while open. */
  children: React.ReactElement;
}
export declare function Tooltip(props: TooltipProps): JSX.Element;
