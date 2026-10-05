/** Short confirmation in the bottom-right corner (wrap in .od-toast-region). Icon plus text, white surface, soft shadow; dismisses itself after 6 s and has a close button. Polite live region. Maps to shadcn Sonner/Toast. Never use it for errors that need action. */
export interface ToastProps {
  message: string;
  tone?: 'success' | 'info';
  /** ms before auto-dismiss; 0 keeps it until closed. */
  duration?: number;
  onDismiss?: () => void;
  className?: string;
}
export declare function Toast(props: ToastProps): JSX.Element;
