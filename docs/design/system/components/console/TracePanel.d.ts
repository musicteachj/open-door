export interface TraceTool { label: string; name: string; ms: string; status?: 'ok' | 'failed'; }
export interface TraceSection { num: string; title: string; cited: boolean; }
/** One turn's trace, docked at --panel-width. Facts only, never content. */
export declare function TracePanel(props: {
  id?: string; title: string; outcome?: 'answered' | 'not-covered' | 'refused' | 'stopped' | 'failed' | 'cap' | 'safety-unavailable'; category?: string;
  safety?: { category?: string; ms?: string; injection?: boolean }; tools?: TraceTool[]; sections?: TraceSection[]; card?: string;
  model?: { id: string; effort: string; prompt: string; tools: string; fallback?: string };
  tokens?: { input: string; cached?: string; output: string; cacheWrites: string }; cost?: string;
  timings?: { safety: string; firstToken: string; total: string }; onClose?: () => void; headingRef?: React.Ref<HTMLHeadingElement>;
}): JSX.Element;
