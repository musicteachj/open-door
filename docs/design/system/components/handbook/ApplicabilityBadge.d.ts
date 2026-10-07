/** Who a handbook section applies to. One label from up to three parts: "Everyone", a state ("California employees"), an employment type ("Hourly staff"), a location ("Denver HQ"), or combined ("Hourly staff in California"). The chip reads "Applies to: …"; the text variant is the bare value for the section list column. */
export interface ApplicabilityBadgeProps {
  /** Two-letter state code: CA, CO, TX. */
  state?: string;
  /** "Hourly staff" or "Salaried staff". */
  type?: string;
  /** "Denver HQ", "Oakland store", "Austin warehouse". */
  location?: string;
  /** Overrides the built label. */
  label?: string;
  variant?: 'chip' | 'text';
  className?: string;
}
export declare function ApplicabilityBadge(props: ApplicabilityBadgeProps): JSX.Element;
export declare function appliesLabel(parts: { state?: string; type?: string; location?: string }): string;
