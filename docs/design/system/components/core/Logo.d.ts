/** Open Door mark (an open doorway in an aubergine tile) with the wordmark and the customer's name. */
export interface LogoProps {
  /** Customer organization shown under the wordmark. Pass null to hide. */
  org?: string | null;
  showWordmark?: boolean;
  /** Mark size in px. 32 in the sidebar. */
  size?: number;
}
export declare function Logo(props: LogoProps): JSX.Element;
