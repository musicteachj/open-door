export interface TurnRow { id: string; time: string; asker: 'Employee' | 'Manager' | 'HR'; location: string; outcome?: 'answered' | 'not-covered' | 'refused' | 'stopped' | 'failed' | 'cap' | 'safety-unavailable'; outcomeLabel?: string; offeredCard?: boolean; injection?: boolean; tools: string; cited?: string; cost: string; firstToken: string; state?: 'hover' | 'focus' | 'selected'; }
/** The sandbox's turns, newest first. Flagged turns render after the timed rows as plain, unfocusable text. */
export declare function TurnTable(props: { id?: string; heading?: string; rows?: TurnRow[]; flagged?: { facts: string }; selectedId?: string; onOpen?: (id: string) => void; panelOpen?: boolean; loading?: boolean }): JSX.Element;
export declare function SafetyLabel(props: { category?: string; ms?: string; injection?: boolean; stacked?: boolean }): JSX.Element;
export declare function InjectionTag(props: { stacked?: boolean }): JSX.Element;
