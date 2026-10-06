/** Label and value row inside a DetailList. Locked rows show a lock and who can see the field, never the value. */
export interface DetailRowProps {
  label: string;
  value?: React.ReactNode;
  /** Hide the value and show the reason instead. Never send the value to the client when locked. */
  locked?: boolean;
  /** e.g. "Visible to Leo and HR". */
  reason?: string;
  /** Rich value, e.g. a manager link. */
  children?: React.ReactNode;
}
export declare function DetailRow(props: DetailRowProps): JSX.Element;
