/** Initials in a primary-tint circle. Decorative (aria-hidden): the name always sits beside it as text. Sizes 40 (cards), 36 (persona switcher), 32 (rows). muted uses surface-hover, for a canceled or inactive item. Maps to shadcn Avatar with AvatarFallback only; no photos in the product. */
export interface AvatarProps {
  initials: string;
  size?: 32 | 36 | 40;
  muted?: boolean;
  className?: string;
}
export declare function Avatar(props: AvatarProps): JSX.Element;
