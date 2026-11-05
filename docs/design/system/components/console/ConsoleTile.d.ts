/** One sandbox figure on the AI Ops console. Plain ink always; "Small sample" goes in foot, in words. */
export declare function ConsoleTile(props: {
  id?: string; title: string; pre?: string; figure?: string; lines?: string[];
  rows?: [string, string][]; closest?: string[]; spend?: string; foot?: string;
  state?: 'default' | 'empty' | 'loading';
}): JSX.Element;
