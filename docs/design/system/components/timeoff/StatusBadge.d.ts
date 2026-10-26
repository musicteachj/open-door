/** Status of a time-off request. Five fixed statuses, each a glyph plus its word: waiting (cinnamon clock), approved (success circle-check), denied (ink circle-x; a decision, never red), recorded (success clipboard-check), canceled (muted ban, muted text). White fill, border-strong edge, 24 px. Maps to shadcn Badge (variant outline). */
export interface StatusBadgeProps {
  status: 'waiting' | 'approved' | 'denied' | 'recorded' | 'canceled';
  className?: string;
}
export declare function StatusBadge(props: StatusBadgeProps): JSX.Element;
