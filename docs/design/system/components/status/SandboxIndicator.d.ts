/** Quiet pill telling demo visitors when their private sandbox resets. Informational only, never alarming. */
export interface SandboxIndicatorProps {
  /** Whole hours remaining. */
  hours?: number;
  /** Override the full label. */
  label?: string;
  className?: string;
}
export declare function SandboxIndicator(props: SandboxIndicatorProps): JSX.Element;
