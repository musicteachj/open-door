/** One suggested question under the composer. Hover fills with the primary tint; focus shows the ring. Selecting fills the composer; the person still sends it. */
export interface TryAskingRowProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'onSelect'> {
  question: string;
  onSelect?: (question: string) => void;
}
export declare function TryAskingRow(props: TryAskingRowProps): JSX.Element;
