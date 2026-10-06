import { cn } from '@/lib/utils'

type LogoProps = {
  /** The customer's name, under the product name. Leave it out before sign-in. */
  customerName?: string
  /** The mark's size in px. 32 in the sidebar. */
  size?: number
  className?: string
}

/** The open-doorway mark with the product name and, once signed in, the customer's. From Logo.jsx. */
function Logo({ customerName, size = 32, className }: LogoProps) {
  return (
    <div data-slot="logo" className={cn('flex items-center gap-3', className)}>
      <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className="flex-none">
        <rect width="32" height="32" rx="9" className="fill-primary" />
        <path d="M13.5 32V17a3 3 0 0 1 3-3h5a3 3 0 0 1 3 3v15z" className="fill-surface" />
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
