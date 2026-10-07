/** Whether a section applies to the current person. Yes: primary check plus "Applies to you" in ink. No: muted minus plus "Doesn't apply to you", never a warning style. Always text plus icon, so color is never the only signal. */
export interface AppliesMarkerProps {
  applies: boolean;
  className?: string;
}
export declare function AppliesMarker(props: AppliesMarkerProps): JSX.Element;
