import { cn } from '@/lib/utils'

type LogoProps = {
  /** The customer's name, under the product name. Leave it out before sign-in. */
  customerName?: string
  /** The mark's size in px. 32 in the sidebar. */
  size?: number
  className?: string
}

/** The door-ajar mark with the product name and, once signed in, the customer's. From Logo.jsx. */
function Logo({ customerName, size = 32, className }: LogoProps) {
  return (
    <div data-slot="logo" className={cn('flex items-center gap-3', className)}>
      <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className="flex-none">
        {/* Door ajar: the tile, the doorway, and the open door's wedge. The same mark as
            docs/design/system/assets/logo-mark.svg and the favicons in public/. */}
        <rect width="32" height="32" rx="9" className="fill-primary" />
        <path d="M9 8H20a3 3 0 0 1 3 3V32H9z" className="fill-surface" />
        <path d="M11 10L17.5 12.5V29.5L11 32z" className="fill-primary" />
      </svg>
      <div className="flex flex-col gap-0.5">
        {/* The sketch's 16/20 name has no step in the type scale, as with the small avatar. */}
        <span className="text-[16px] leading-5 font-semibold tracking-[-0.01em] text-ink">
          Open Door
        </span>
        {/* An explicit space, so the two names read apart where text runs on (jsdom, copy). */}
        {customerName && ' '}
        {customerName && <span className="text-caption text-ink-muted">{customerName}</span>}
      </div>
    </div>
  )
}

export { Logo }
export type { LogoProps }
