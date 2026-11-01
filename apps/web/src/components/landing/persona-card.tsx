import { ArrowRight, LoaderCircle, MapPin } from 'lucide-react'
import { initialsOf } from '@/lib/initials'
import { cn } from '@/lib/utils'

type PersonaCardProps = {
  name: string
  role: string
  location: string
  /** One line on what to try as this person. */
  prompt: string
  initials?: string
  /** `starting` is this card's own sandbox being created. */
  status?: 'idle' | 'starting'
  /** Another card is starting, so this one is unavailable. Not the same as `starting`. */
  disabled?: boolean
  onSelect: () => void
  startLabel?: string
  startingLabel?: string
  className?: string
}

/**
 * One person in the landing page's "Choose who to be" picker, from PersonaCard.jsx. One button,
 * named by what it shows. While `starting` it is busy but stays enabled, so keyboard focus
 * is not dropped (the sketch disables it; the notes ask only for the other cards to be disabled),
 * and a second click does nothing. The start is announced in a polite live region.
 */
function PersonaCard({
  name,
  role,
  location,
  prompt,
  initials,
  status = 'idle',
  disabled = false,
  onSelect,
  startLabel,
  startingLabel = 'Setting up Juniper Row…',
  className,
}: PersonaCardProps) {
  const starting = status === 'starting'
  return (
    <>
      <button
        type="button"
        data-slot="persona-card"
        aria-busy={starting || undefined}
        disabled={disabled}
        onClick={() => {
          if (!starting) onSelect()
        }}
        className={cn(
          'group relative flex w-full cursor-pointer flex-col items-stretch rounded-lg border border-border bg-surface-raised p-6 text-left text-ink transition-[border-color,box-shadow]',
          // Gated on !starting: a starting card stays enabled, so the hover border would beat primary.
          !starting && 'enabled:hover:border-input-border-hover',
          starting && 'cursor-progress border-primary shadow-[0_0_0_1px_var(--color-primary)]',
          'disabled:cursor-not-allowed disabled:border-border-subtle disabled:text-disabled-fg',
          className,
        )}
      >
        <span
          aria-hidden="true"
          className="flex size-10 items-center justify-center rounded-full bg-primary-tint text-ui font-semibold text-ink group-disabled:bg-disabled-bg group-disabled:text-disabled-fg"
        >
          {initials ?? initialsOf(name)}
        </span>
        <span className="mt-4 text-body-lg font-semibold">{name}</span>
        {/* Hidden pauses: "Priya Raman, Visual Merchandiser, Oakland store. <prompt> Start as Priya". */}
        <span className="sr-only">,</span> <span className="text-ui">{role}</span>
        <span className="sr-only">,</span>{' '}
        <span className="mt-1 flex items-center gap-1.5 text-small text-ink-muted group-disabled:text-disabled-fg">
          <MapPin aria-hidden="true" className="size-3.5" />
          {location}
        </span>
        <span className="sr-only">.</span>{' '}
        <span aria-hidden="true" className="my-5 h-px bg-border-subtle" />
        <span className="flex-1 text-body">{prompt}</span>{' '}
        <span className="mt-5 flex min-h-5 items-center gap-2 text-small font-semibold text-primary group-disabled:text-disabled-fg">
          {starting ? (
            <>
              <LoaderCircle aria-hidden="true" className="size-4 animate-spin text-primary" />
              <span className="text-ink">{startingLabel}</span>
            </>
          ) : (
            <>
              {startLabel ?? `Start as ${name.split(' ')[0]}`}
              <ArrowRight aria-hidden="true" className="size-4" />
            </>
          )}
        </span>
      </button>
      <output className="sr-only">{starting ? startingLabel : ''}</output>
    </>
  )
}

export { PersonaCard }
export type { PersonaCardProps }
