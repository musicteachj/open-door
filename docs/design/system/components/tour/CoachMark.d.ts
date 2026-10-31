/** One guided-tour step: a non-modal dialog beside its target. */
export declare function CoachMark(props: {
  id?: string; step: number; total?: number; title: string; body: string; missing?: string;
  chips?: string[]; sent?: number[]; resultShown?: boolean; side?: 'bottom' | 'top' | 'right'; pointer?: number;
  onBack?: () => void; onNext?: () => void; onSkip?: () => void; onLeave?: () => void; onSend?: (index: number) => void;
  headingRef?: React.Ref<HTMLHeadingElement>; style?: React.CSSProperties; className?: string;
}): JSX.Element;
/** The 2 px primary ring drawn 4 px outside the target. */
export declare function TourRing(props: { rect?: { x: number; y: number; w: number; h: number }; radius?: number }): JSX.Element | null;
