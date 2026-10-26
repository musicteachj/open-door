import { CircleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

// The pieces every time-off field shares (.od-field-label, .od-field-hint, .od-field-error).

export const fieldLabelClass = 'text-ui font-semibold text-ink'
export const fieldHintClass = 'text-small text-ink-muted'

/** A 32 px icon button with a quiet hover and the focus ring: the picker's month arrows and the form's Close. */
export const iconButtonClass =
  'flex size-8 flex-none cursor-pointer items-center justify-center rounded-sm border-0 bg-transparent text-ink transition-colors outline-none hover:bg-neutral-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus-ring focus-visible:outline-solid'

/** A field's error: the icon and the words, announced when it appears. */
export function FieldError({
  id,
  className,
  children,
}: {
  id?: string
  className?: string
  children: ReactNode
}) {
  return (
    <p
      id={id}
      role="alert"
      className={cn('m-0 flex items-center gap-1.5 text-small text-danger', className)}
    >
      <CircleAlert aria-hidden="true" className="size-3.5 flex-none" />
      {children}
    </p>
  )
}
