/** Inline message inside a form. warning: amber tint, triangle-alert, role="status"; the action still works. refusal: red tint, circle-alert, role="alert"; the submit button is disabled. Text is always ink. */
export interface FormMessageProps { tone?: 'warning' | 'refusal'; children: React.ReactNode; }
export declare function FormMessage(props: FormMessageProps): JSX.Element;
