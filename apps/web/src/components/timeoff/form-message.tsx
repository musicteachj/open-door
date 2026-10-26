import { CircleAlert, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

type FormMessageProps = {
  /** `warning` is advice the form lets a person ignore; `refusal` is a no that blocks the request. */
  tone: 'warning' | 'refusal'
  /** A refusal is an alert by default. Pass false for one already there when the page opened. */
  announce?: boolean
  children: ReactNode
  className?: string
}

/**
 * A message in the request form (FormMessage.jsx). A warning is a polite status on the amber tint
 * and never blocks the button; a refusal is an alert on the danger tint. The words are always ink:
 * the icon's color and the border are decoration, since the border is only 1.6:1 against white.
 */
function FormMessage({ tone, announce = true, children, className }: FormMessageProps) {
  const refusal = tone === 'refusal'
  const Icon = refusal ? CircleAlert : TriangleAlert
  return (
    <div
      data-slot="form-message"
      data-tone={tone}
      role={refusal ? (announce ? 'alert' : undefined) : 'status'}
      className={cn(
        'flex items-start gap-2.5 rounded-md border px-3.5 py-3',
        refusal ? 'border-danger-border bg-danger-tint' : 'border-warning-border bg-warning-tint',
        className,
      )}
    >
      <Icon
        aria-hidden="true"
        className={cn('mt-0.5 size-4 flex-none', refusal ? 'text-danger' : 'text-warning')}
      />
      <p className="m-0 text-ui font-regular text-pretty text-ink">{children}</p>
    </div>
  )
}

export { FormMessage }
export type { FormMessageProps }
