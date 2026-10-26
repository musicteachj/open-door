export interface CaseTimelineEvent { text: string; time: string; }
/** A case's events, oldest first. The latest has a primary dot. */
export declare function CaseTimeline(props: { id?: string; events: CaseTimelineEvent[]; announce?: string }): JSX.Element;
