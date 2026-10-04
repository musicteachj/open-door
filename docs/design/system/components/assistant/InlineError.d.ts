/** Calm inline error under the control it belongs to: danger icon and text, plus an optional secondary Retry. Red means an error only. */
export interface InlineErrorProps {
  message?: string;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
}
export declare function InlineError(props: InlineErrorProps): JSX.Element;
