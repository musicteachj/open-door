/** Open Door mark (a door ajar in an aubergine tile; sizes of 16 or less use the pixel-aligned 16 px drawing) with the wordmark and the customer's name. */
export interface LogoProps {
  /** Customer organization shown under the wordmark. Pass null to hide. */
  org?: string | null;
  showWordmark?: boolean;
  /** Mark size in px. 32 in the sidebar. */
  size?: number;
}
export declare function Logo(props: LogoProps): JSX.Element;
