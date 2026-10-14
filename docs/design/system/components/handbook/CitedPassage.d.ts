/** The highlighted paragraph a citation points to. Primary-tint ground with ink text (13.0:1), labeled "Cited passage" with a quote icon and a slim 3 px cinnamon (--marker) bar inset on its left edge, which keeps it distinct from hover and selected tints. The label and icon carry the meaning; the bar is reinforcement, so color isn't the only signal. A region labeled by that text, so screen readers hear "Cited passage" first. On a deep link (/handbook/CA-4.3?passage=p2) pass autoFocus: it scrolls into view and takes focus. compact is the 15 px version for the passage panel. */
export interface CitedPassageProps {
  children: React.ReactNode;
  /** Shows "Clear highlight" (handbook page only). */
  onClear?: () => void;
  compact?: boolean;
  autoFocus?: boolean;
  id?: string;
  className?: string;
}
export declare function CitedPassage(props: CitedPassageProps): JSX.Element;
