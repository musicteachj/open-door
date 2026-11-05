import { Info } from 'lucide-react'
import { Navigate } from 'react-router'
import { useMe } from '@/app/useMe'
import { useStartSandbox } from '@/app/useStartSandbox'
import { Logo } from '@/components/core/logo'
import { InlineError } from '@/components/feedback/inline-error'
import { PersonaCard } from '@/components/landing/persona-card'
import { TourStartButton } from '@/components/tour/tour-start-button'
import { useStartTour } from '@/features/tour/use-start-tour'
import { PERSONAS } from '@/features/personas/personas'
import { ApiError } from '@/lib/api-fetch'
import { AI_DISCLOSURE } from '@/lib/disclosure'
import { SANDBOX_START_FAILED } from '@/lib/sandbox-copy'

// From docs/design/screens/01-landing/notes.md. Nothing here is the signed-in person's: the
// landing page is outside the session guard, so it is not remounted by a reset.

const HEADLINE = 'Your open-door policy, now always open.'
const PITCH =
  'An AI help desk for HR questions. It answers with citations to the company handbook, proposes actions for a person to confirm, and sends sensitive topics like harassment or medical leave to a human HR partner.'
const SANDBOX_NOTE =
  'Each visit gets its own private copy of Juniper Row, a fictional company. It resets after 24 hours.'
const NOTICE =
  "Juniper Row and everyone in it are fictional. This is a demo, not legal advice. Don't enter real personal information."

export function LandingPage() {
  const me = useMe()
  const start = useStartSandbox()
  const tour = useStartTour()

  // A signed-in visitor has nothing to choose. Cached data whose latest fetch was a 401 is not a
  // signed-in visitor: the sandbox ended, and sending them on would bounce them to the reset page.
  const unauthorized = me.error instanceof ApiError && me.error.status === 401
  if (me.data && !unauthorized) return <Navigate to="/ask" replace />
  if (me.isPending) return <output className="sr-only">Loading…</output>

  // Either start forgets the other's failure, so only one error is ever shown.
  const startTour = () => {
    start.reset()
    tour.start()
  }
  const startingKey = start.isPending ? start.variables?.data?.persona : undefined
  // While the tour's sandbox starts, all four cards are unavailable; while a card's does, the tour
  // button is.
  const cardsDisabled = tour.starting

  return (
    <div className="flex min-h-dvh flex-col bg-surface px-6 text-ink">
      <div className="mx-auto flex w-full max-w-292 flex-1 flex-col">
        <header className="py-6">
          <Logo />
        </header>

        <main className="pt-16">
          <h1 className="m-0 max-w-144 text-display text-balance">{HEADLINE}</h1>
          <p className="mt-5 max-w-180 text-body-lg text-ink-muted">{PITCH}</p>

          <h2 className="mt-16 mb-5 text-h2">Choose who to be</h2>
          <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-4 p-0">
            {PERSONAS.map((persona) => (
              <li key={persona.key} className="flex">
                <PersonaCard
                  className="h-full"
                  name={persona.name}
                  role={persona.title}
                  location={persona.location}
                  prompt={persona.cardPrompt}
                  initials={persona.initials}
                  status={startingKey === persona.key ? 'starting' : 'idle'}
                  disabled={
                    cardsDisabled || (startingKey !== undefined && startingKey !== persona.key)
                  }
                  onSelect={() => {
                    tour.dismissError()
                    start.mutate({ data: { persona: persona.key } })
                  }}
                />
              </li>
            ))}
          </ul>
          {/* One error at a time: starting either way forgets the other's failure. */}
          {start.isError && (
            <InlineError
              message={SANDBOX_START_FAILED}
              onRetry={() => start.mutate(start.variables)}
            />
          )}
          {tour.failed && <InlineError message={SANDBOX_START_FAILED} onRetry={startTour} />}

          <div className="mt-6 flex flex-wrap items-center justify-between gap-x-6 gap-y-4">
            <p className="m-0 text-small text-ink-muted">{SANDBOX_NOTE}</p>
            <TourStartButton starting={tour.starting} disabled={tour.blocked} onStart={startTour} />
          </div>
        </main>
      </div>

      <footer className="mx-auto mt-16 w-full max-w-292">
        <div className="flex flex-col gap-1 border-t border-border py-6 text-small text-ink-muted">
          <p className="m-0 flex items-center gap-2">
            <Info aria-hidden="true" className="size-4 shrink-0" />
            {AI_DISCLOSURE}
          </p>
          <p className="m-0 pl-6">{NOTICE}</p>
        </div>
      </footer>
    </div>
  )
}
