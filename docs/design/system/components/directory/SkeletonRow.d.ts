/** Placeholder row in the directory's column layout while people load. Static gray bars, no shimmer. Decorative; the container sets aria-busy and announces loading. */
export interface SkeletonRowProps {
  /** Varies bar widths so a stack doesn't look striped. */
  variant?: number;
}
export declare function SkeletonRow(props: SkeletonRowProps): JSX.Element;
