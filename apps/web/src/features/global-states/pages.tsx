import { useQueryClient } from '@tanstack/react-query'
import { ArrowRight, RotateCcw } from 'lucide-react'
import { Link, useNavigate } from 'react-router'
import { FullPageMessage } from '@/components/feedback/full-page-message'
import { Button } from '@/components/ui/button'
import { buttonVariants } from '@/components/ui/button-variants'
import { resetIdentity } from '@/lib/identity'
import { cn } from '@/lib/utils'

// The three global states, from docs/design/screens/05-global-states/notes.md. Each is a
// FullPageMessage, so its title is the page's h1 and takes focus. Outside the shell they fill the
// window (`h-dvh`) under their own landmark; inside, they fill the shell's content sheet, which
// supplies the landmark.

function Window({ children }: { children: React.ReactNode }) {
  return <main className="h-dvh bg-surface">{children}</main>
}

/** The sandbox's 24 hours are up. Outside the shell: the session it belonged to is gone. */
export function SessionExpired() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  return (
    <Window>
      <FullPageMessage
        outsideShell
        title="This sandbox has reset."
        body="Sandboxes last 24 hours. Start a new one to keep exploring."
      >
        <Button
          onClick={() => {
            // The landing page must not find the old person in the cache and send them back.
            resetIdentity(queryClient)
            void navigate('/')
          }}
        >
          Choose who to be
          <ArrowRight aria-hidden="true" className="size-4" />
        </Button>
      </FullPageMessage>
    </Window>
  )
}

/** An unknown route, or a person or page the API reports as not found. Inside the shell. */
export function NotFound() {
  return (
    <FullPageMessage title="We couldn't find that page.">
      <Link to="/ask" className={cn(buttonVariants(), 'no-underline')}>
        Go to Ask
      </Link>
    </FullPageMessage>
  )
}

type SomethingWentWrongProps = {
  /** The response's full X-Request-ID. Left out for a network failure, which has none. */
  requestId?: string | null
  /** Repeats what failed. */
  onRetry: () => void
  /** True only when the shell itself could not load. */
  outsideShell?: boolean
}

/** An unexpected failure: a 5xx or a network error. */
export function SomethingWentWrong({
  requestId,
  onRetry,
  outsideShell = false,
}: SomethingWentWrongProps) {
  const message = (
    <FullPageMessage
      outsideShell={outsideShell}
      title="Something went wrong on our side."
      body={
        requestId
          ? 'Try again in a moment. If it keeps happening, this reference helps us find it:'
          : 'Try again in a moment.'
      }
      reference={requestId ?? undefined}
    >
      <Button onClick={onRetry}>
        <RotateCcw aria-hidden="true" className="size-4" />
        Retry
      </Button>
    </FullPageMessage>
  )
  return outsideShell ? <Window>{message}</Window> : message
}
