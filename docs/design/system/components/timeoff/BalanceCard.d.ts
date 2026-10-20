/** One balance as a plain record: label, big figure (40 px, tabular) with days beside it, a source chip to the handbook section, a ledger (dl) that adds up to the figure, and footer lines (next accrual, cap, renewal). notice sits above the ledger, e.g. at the PTO ceiling; the ledger and footer stay. loading renders static skeleton bars. Maps to shadcn Card. */
export interface BalanceCardProps {
  id?: string;
  label?: string;
  hours?: string;
  days?: string;
  rows?: { label: string; value: string }[];
  footer?: string[];
  source?: { href: string; label: string; state?: string };
  notice?: string;
  loading?: boolean;
}
export declare function BalanceCard(props: BalanceCardProps): JSX.Element;
