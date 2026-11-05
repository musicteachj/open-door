/** A prompt chip in a coach mark. Sends the text as the current persona; then shows "Sent" and is aria-disabled. */
export declare function TourChip(props: { text: string; sent?: boolean; onSend?: (text: string) => void; state?: 'hover' | 'focus' }): JSX.Element;
