import { cva, type VariantProps } from 'class-variance-authority'
import { Avatar as AvatarPrimitive } from 'radix-ui'
import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

// The design's avatar (navigation.css): a circle on the primary tint with semibold initials,
// 36 px in a list and 28 px in a menu (whose initials are 11 px, between the scale's steps). The
// approvals screen adds 40 px (`lg`, a card's requester, 14/20) and 32 px (`row`, a person in a
// compact row, 12/16), and a muted fill for a person who is not the subject (.od-avatar).
const avatarVariants = cva('group/avatar relative flex shrink-0 overflow-hidden rounded-full', {
  variants: { size: { lg: 'size-10', md: 'size-9', row: 'size-8', sm: 'size-7' } },
  defaultVariants: { size: 'md' },
})

/**
 * Initials fall back when there is no photo. An avatar beside a person's name is decoration:
 * pass `aria-hidden="true"`, as the design's persona menu does.
 */
function Avatar({
  className,
  size,
  muted = false,
  ...props
}: ComponentProps<typeof AvatarPrimitive.Root> &
  VariantProps<typeof avatarVariants> & {
    /** Fills with the hover surface instead of the primary tint. */
    muted?: boolean
  }) {
  return (
    <AvatarPrimitive.Root
      data-slot="avatar"
      data-size={size ?? 'md'}
      data-muted={muted ? '' : undefined}
      className={cn(avatarVariants({ size }), className)}
      {...props}
    />
  )
}

function AvatarImage({ className, ...props }: ComponentProps<typeof AvatarPrimitive.Image>) {
  return (
    <AvatarPrimitive.Image
      data-slot="avatar-image"
      className={cn('aspect-square size-full', className)}
      {...props}
    />
  )
}

function AvatarFallback({ className, ...props }: ComponentProps<typeof AvatarPrimitive.Fallback>) {
  return (
    <AvatarPrimitive.Fallback
      data-slot="avatar-fallback"
      className={cn(
        'flex size-full items-center justify-center rounded-full bg-primary-tint text-small font-semibold text-ink',
        'group-data-[size=sm]/avatar:text-[11px]',
        'group-data-[size=lg]/avatar:text-ui group-data-[size=row]/avatar:text-caption',
        'group-data-[muted]/avatar:bg-surface-hover',
        className,
      )}
      {...props}
    />
  )
}

export { Avatar, AvatarFallback, AvatarImage }
