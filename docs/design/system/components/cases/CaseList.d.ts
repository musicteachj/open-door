export interface CaseRow {
  id?: string;
  category: string;
  sent: string;
  status: 'case-sent' | 'case-reviewing' | 'case-finished';
  line: string;
}
/** My cases list. Status only; no links into a case, never the words. */
export declare function CaseList(props: { cases: CaseRow[] }): JSX.Element;
