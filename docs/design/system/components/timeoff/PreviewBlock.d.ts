/** Live preview under the request fields: counted days (primary check, hours on the right), skipped days with the reason (muted calendar-minus icon), days already booked (danger circle-alert, "Already booked"), then the total amount and what's left. aria-live="polite" so changes are read. empty shows a one-line prompt instead. */
export interface PreviewBlockProps {
  id?: string;
  /** blocked: the day is already booked; shows the error icon and "Already booked" instead of hours. */
  counted?: { label: string; hours?: string; blocked?: boolean }[];
  skipped?: string[];
  amount?: string;
  /** Omit when a refusal applies. */
  left?: string;
  /** Rules the preview used, as source chips: §4.1 for PTO, plus §4.2 when a holiday is skipped; CA-4.3 for Priya's sick time. */
  sources?: { label: string; href: string }[];
  empty?: boolean;
}
export declare function PreviewBlock(props: PreviewBlockProps): JSX.Element;
