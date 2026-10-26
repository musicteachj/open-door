/** Status of a time-off request. Five fixed statuses, each a glyph plus its word: waiting (cinnamon clock), approved (success circle-check), denied (ink circle-x; a decision, never red), recorded (success clipboard-check), canceled (muted ban, muted text). Case statuses for My cases: case-sent "Sent to HR" (cinnamon clock), case-reviewing "HR is reviewing" (primary file-search), case-finished "HR has finished its review" (ink circle-check; neutral, not a success). HR side: case-new "New" (cinnamon dot), case-in-review "In review" (primary file-search), case-closed "Closed" (ink circle-check). White fill, border-strong edge, 24 px. Maps to shadcn Badge (variant outline). */
export interface StatusBadgeProps {
  status: 'waiting' | 'approved' | 'denied' | 'recorded' | 'canceled' | 'case-sent' | 'case-reviewing' | 'case-finished' | 'case-new' | 'case-in-review' | 'case-closed';
  className?: string;
}
export declare function StatusBadge(props: StatusBadgeProps): JSX.Element;
