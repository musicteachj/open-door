import { Clock } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

type SandboxIndicatorProps = {
  /** The text, such as "Sandbox resets in 21 h". */
  children: ReactNode
  className?: string
}

/** The pill that says this is a sandbox and when it resets. From SandboxIndicator.jsx. */
function SandboxIndicator({ children, className }: SandboxIndicatorProps) {
  return (
    <span
      data-slot="sandbox-indicator"
      className={cn(
        'inline-flex h-7 items-center gap-2 rounded-full border border-border bg-surface-raised px-3 text-caption whitespace-nowrap text-ink-muted',
        className,
      )}
    >
      <Clock aria-hidden="true" className="size-[13px]" />
      {children}
    </span>
  )
}

export { SandboxIndicator }
export type { SandboxIndicatorProps }
