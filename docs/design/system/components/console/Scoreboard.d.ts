export interface ScoreboardSet { name: string; src?: string; fig?: string; cap?: string; low?: string | null; lowNote?: string; other?: string[]; placeholder?: string; }
/** The AI Ops console's eval scoreboard, made self-contained (data bundled). */
export declare function Scoreboard(props: { id?: string; sets?: ScoreboardSet[]; runs?: (string | null)[][] }): JSX.Element;
export declare function ScoreboardSetRow(props: { set: ScoreboardSet }): JSX.Element;
