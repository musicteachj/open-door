import { ArrowLeft } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { cn } from '@/lib/utils'

type PageHeaderProps = {
  /** Content on the right, usually the sandbox indicator. */
  right?: ReactNode
  className?: string
} & (
  | {
      /** The page's h1. */
      title: string
      /** Beside the title, such as "44 of 120 people". */
      count?: string
      back?: never
    }
  | {
      /** A back link in place of the title, for a page that opens from a list. */
      back: { to: string; label: string }
      title?: never
      count?: never
    }
)

/**
 * The top of a page: the title with an optional count, or a back link, and a slot on the right.
 * From the directory frames in docs/design/system/Directory.dc.html, which has no component
 * sketch for it. The profile's back link is a ghost-sized link with a neutral hover.
 */
function PageHeader({ title, count, back, right, className }: PageHeaderProps) {
  return (
    <header
      data-slot="page-header"
      className={cn('flex flex-wrap items-start justify-between gap-x-6 gap-y-3', className)}
    >
      {back ? (
        <Link
          to={back.to}
          aria-label={`Back to ${back.label}`}
          className="-ml-1.5 inline-flex h-control-sm items-center gap-1.5 rounded-sm pr-2.5 pl-1.5 text-ui font-medium text-ink-nav no-underline transition-[color,background-color] hover:bg-neutral-hover hover:text-ink"
        >
          <ArrowLeft aria-hidden="true" className="size-4" />
          {back.label}
        </Link>
      ) : (
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-3">
          <h1 className="text-h1 wrap-break-word text-ink">{title}</h1>
          {count && <span className="text-body text-ink-muted">{count}</span>}
        </div>
      )}
      {right}
    </header>
  )
}

export { PageHeader }
export type { PageHeaderProps }
