import { ChevronsUpDown, LoaderCircle } from 'lucide-react'
import { useState, type ComponentProps } from 'react'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useIsTruncated } from '@/hooks/use-is-truncated'
import { initialsOf } from '@/lib/initials'
import { personaSwitcherLabel } from '@/lib/labels'
import { cn } from '@/lib/utils'

type PersonaSwitcherProps = Omit<ComponentProps<'button'>, 'children'> & {
  /** Leave both out when no one is current: the switcher shows "Choose a persona". */
  name?: string
  title?: string
  initials?: string
  /** While a switch runs: a spinner and this text on one line, such as "Switching to Marcus…". */
  busyLabel?: string
}

/**
 * The button at the bottom of the sidebar that opens the persona menu. Its name always holds the
 * full title. The title truncates, and the tooltip shows it in full only when it is truncated.
 * It spreads its props onto the button, so a menu trigger can wrap it. From PersonaSwitcher.jsx.
 */
function PersonaSwitcher({
  name,
  title,
  initials,
  busyLabel,
  className,
  ...props
}: PersonaSwitcherProps) {
  const [titleRef, truncated] = useIsTruncated<HTMLSpanElement>(title)
  // The same rule as PersonaMenu's: any busyLabel, even an empty one, means a switch is pending.
  const busy = busyLabel !== undefined
  // Always controlled, so Radix never switches modes. It reports focus and hover; we add the rest.
  const [open, setOpen] = useState(false)
  return (
    <Tooltip open={open && truncated && !busy} onOpenChange={setOpen}>
      <TooltipTrigger asChild>
        <button
          type="button"
          data-slot="persona-switcher"
          aria-busy={busy || undefined}
          // Not `disabled`: that would drop keyboard focus. It just looks and reports as inactive.
          aria-disabled={busy || undefined}
          aria-label={busy ? busyLabel : personaSwitcherLabel(name, title)}
          // min-h-[61px] is the sketch's height (.od-persona__btn); the spacing scale has no 61 px step.
          className={cn(
            'flex min-h-[61px] w-full cursor-pointer items-center gap-3 border-0 border-t border-t-border bg-transparent px-2 py-3 text-left text-ink transition-[color,background-color] hover:bg-neutral-hover aria-disabled:cursor-default aria-disabled:hover:bg-transparent aria-expanded:bg-neutral-hover',
            className,
          )}
          {...props}
        >
          {busy ? (
            <>
              <span className="flex size-9 flex-none items-center justify-center">
                <LoaderCircle aria-hidden="true" className="size-4 animate-spin text-primary" />
              </span>
              <span className="min-w-0 flex-1 truncate text-small text-ink-muted">{busyLabel}</span>
            </>
          ) : (
            <>
              <Avatar aria-hidden="true">
                <AvatarFallback>{initials ?? (name ? initialsOf(name) : '?')}</AvatarFallback>
              </Avatar>
              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="truncate text-ui leading-4.5 font-semibold">
                  {name ?? 'Choose a persona'}
                </span>
                {title !== undefined && (
                  <span ref={titleRef} className="truncate text-caption text-ink-muted">
                    {title}
                  </span>
                )}
              </span>
              <ChevronsUpDown aria-hidden="true" className="size-4 flex-none text-ink-muted" />
            </>
          )}
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" align="start">
        {title}
      </TooltipContent>
    </Tooltip>
  )
}

export { PersonaSwitcher }
export type { PersonaSwitcherProps }
