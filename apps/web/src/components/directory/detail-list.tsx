import { Eye, type LucideIcon } from 'lucide-react'
import { useId, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

type DetailListProps = {
  title: string
  /** Beside the title, such as a lock on the private details. */
  icon?: LucideIcon
  /** After the title: "Only Leo and HR can see these." */
  note?: string
  /** Shown whenever values are visible: "Viewing private details is recorded in the audit log." */
  auditNote?: string
  /** `DetailRow`s. */
  children: ReactNode
  className?: string
}

/**
 * A titled group of profile fields, from DetailList.jsx: a region named by its heading, holding
 * a description list in a bordered panel. Every read of private details is audited, so a caller
 * that shows values passes `auditNote`.
 */
function DetailList({ title, icon: Icon, note, auditNote, children, className }: DetailListProps) {
  const headingId = useId()
  return (
    <section data-slot="detail-list" aria-labelledby={headingId} className={className}>
      <div className="mb-3 flex flex-wrap items-center gap-x-2">
        {Icon && <Icon aria-hidden="true" className="size-4 text-ink-muted" />}
        <h2 id={headingId} className="text-body font-semibold">
          {title}
        </h2>
        {note && (
          <span className="text-small text-ink-muted">
            <span aria-hidden="true">· </span>
            {note}
          </span>
        )}
      </div>
      {auditNote && (
        <p
          className={cn(
            'mb-3 flex items-center gap-2 rounded-md border border-border-subtle bg-surface-sunken px-3 py-2.5 text-small text-ink-muted',
          )}
        >
          <Eye aria-hidden="true" className="size-3.5 flex-none" />
          {auditNote}
        </p>
      )}
      <dl className="m-0 rounded-lg border border-border px-5">{children}</dl>
    </section>
  )
}

export { DetailList }
export type { DetailListProps }
