/**
 * The ask box: a large textarea, the persistent AI disclosure, and the labeled Ask button. Border uses input-border (3:1+) at rest,
 * input-border-hover on hover, and the primary border with a focus halo while focused. Enter sends; Shift+Enter adds a line.
 * Ask stays enabled when empty and moves focus to the box instead of sending.
 */
export interface ComposerProps {
  value?: string;
  defaultValue?: string;
  onChange?: (value: string, event: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onSubmit?: (value: string) => void;
  placeholder?: string;
  /** The AI disclosure. Always shown. */
  disclosure?: string;
  submitLabel?: string;
  rows?: number;
  /** Shows InlineError under the composer. */
  error?: string;
  /** Defaults to resubmitting the current value. */
  onRetry?: () => void;
  autoFocus?: boolean;
  className?: string;
  /** Specimens only: data-state="hover" | "focus" on the box. */
  'data-state'?: string;
}
export declare function Composer(props: ComposerProps): JSX.Element;
