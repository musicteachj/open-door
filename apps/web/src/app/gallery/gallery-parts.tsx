import type { ReactNode } from 'react'

// The helpers every gallery section uses. Each state sits under a heading with a stable id, so a
// test can address it.

export function Section({
  id,
  title,
  children,
}: {
  id: string
  title: string
  children: ReactNode
}) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3">
      <h3 id={id} className="text-small font-semibold text-ink-muted">
        {title}
      </h3>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </section>
  )
}

export function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-4 border-t border-border pt-6">
      <h2 className="text-h2 text-ink">{title}</h2>
      {children}
    </section>
  )
}
