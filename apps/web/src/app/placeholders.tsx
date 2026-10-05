import { useQueryClient } from '@tanstack/react-query'
import { Navigate, useNavigate, useParams } from 'react-router'
import { PersonaKey, useCreateSandbox, useEndSession, useSwitchPersona } from '@/api/generated'
import { resetIdentity } from '@/lib/identity'
import { signInAs, useMe } from './useMe'

// Stage 5 replaces the landing page, /ask, not found, and the outside-the-shell pages
// (session expired, something went wrong). Stage 6 replaces the directory pages. Until then these
// are plain markup that proves the routing, the session guard, and the identity reset.

const PERSONAS: { key: PersonaKey; name: string }[] = [
  { key: PersonaKey.priya, name: 'Priya' },
  { key: PersonaKey.marcus, name: 'Marcus' },
]

export function Landing() {
  const me = useMe()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const start = useCreateSandbox({
    mutation: {
      onSuccess: ({ me }) => {
        signInAs(queryClient, me)
        void navigate('/ask')
      },
    },
  })

  // A signed-in visitor has nothing to choose.
  if (me.data) return <Navigate to="/ask" replace />
  if (me.isPending) return <output>Loading…</output>
  return (
    <main className="p-8 text-ink">
      <h1>Open Door</h1>
      {PERSONAS.map(({ key, name }) => (
        <button key={key} type="button" onClick={() => start.mutate({ data: { persona: key } })}>
          Start as {name}
        </button>
      ))}
    </main>
  )
}

export function Ask() {
  const me = useMe()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const switchPersona = useSwitchPersona({
    mutation: { onSuccess: (me) => signInAs(queryClient, me) },
  })
  const signOut = useEndSession({
    mutation: {
      onSuccess: () => {
        resetIdentity(queryClient)
        void navigate('/')
      },
    },
  })
  if (!me.data) return null
  return (
    <main className="p-8 text-ink">
      <h1>Ask</h1>
      <p>
        Signed in as {me.data.givenName} {me.data.familyName}
      </p>
      {PERSONAS.map(({ key, name }) => (
        <button
          key={key}
          type="button"
          onClick={() => switchPersona.mutate({ data: { persona: key } })}
        >
          Switch to {name}
        </button>
      ))}
      <button type="button" onClick={() => signOut.mutate()}>
        Sign out
      </button>
    </main>
  )
}

export function Directory() {
  return (
    <main className="p-8 text-ink">
      <h1>Directory</h1>
    </main>
  )
}

export function Profile() {
  const { personId } = useParams()
  return (
    <main className="p-8 text-ink">
      <h1>Profile</h1>
      <p>{personId}</p>
    </main>
  )
}

export function NotFound() {
  return (
    <main className="p-8 text-ink">
      <h1>We couldn&apos;t find that page.</h1>
      <a href="/ask">Go to Ask</a>
    </main>
  )
}

export function SessionExpired() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  return (
    <main className="p-8 text-ink">
      <h1>This sandbox has reset.</h1>
      <p>Sandboxes last 24 hours. Start a new one to keep exploring.</p>
      <button
        type="button"
        onClick={() => {
          // The landing page must not find the old person in the cache and send them back.
          resetIdentity(queryClient)
          void navigate('/')
        }}
      >
        Choose who to be
      </button>
    </main>
  )
}

export function SomethingWentWrong({ onRetry }: { onRetry: () => void }) {
  return (
    <main className="p-8 text-ink">
      <h1>Something went wrong on our side.</h1>
      <p>Try again in a moment.</p>
      <button type="button" onClick={onRetry}>
        Retry
      </button>
    </main>
  )
}
