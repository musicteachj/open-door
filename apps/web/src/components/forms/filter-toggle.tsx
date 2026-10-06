import { Check, Users } from 'lucide-react'
import { cn } from '@/lib/utils'

type FilterToggleProps = {
  label?: string
  /** How many people the list would show with the toggle on. */
  count?: number
  pressed: boolean
  onChange: (pressed: boolean) => void
  className?: string
}

/**
 * An on/off filter, from FilterToggle.jsx: "My team", for managers only (the page leaves it out
 * for everyone else, never disabled). Pressed state is `aria-pressed`, shown by the tint and a
 * check in place of the icon, so it is not color alone.
 */
function FilterToggle({
  label = 'My team',
  count,
  pressed,
  onChange,
  className,
}: FilterToggleProps) {
  const Icon = pressed ? Check : Users
  return (
    <button
      type="button"
      data-slot="filter-toggle"
      aria-pressed={pressed}
      onClick={() => onChange(!pressed)}
      className={cn(
        'inline-flex h-control cursor-pointer items-center gap-2 rounded-md border border-border-strong bg-surface-raised pr-3.5 pl-3 text-ui font-semibold whitespace-nowrap text-ink',
        'transition-[border-color,background-color] hover:border-border-strong-hover',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus-ring focus-visible:outline-solid',
        'aria-pressed:border-primary-tint aria-pressed:bg-primary-tint',
        className,
      )}
    >
      <Icon
        aria-hidden="true"
        strokeWidth={pressed ? 2 : 1.75}
        className={cn('size-4', pressed ? 'text-primary' : 'text-ink-muted')}
      />
      {label}
      {count != null && ' '}
      {count != null && <span className="font-regular text-ink-muted tabular-nums">{count}</span>}
    </button>
  )
}

export { FilterToggle }
export type { FilterToggleProps }
