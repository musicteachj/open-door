import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { useEndSession, useSwitchPersona, type PersonaKey } from '@/api/generated'
import { signInAs } from '@/app/useMe'
import { PERSONAS, personaFor } from '@/features/personas/personas'
import { resetIdentity } from '@/lib/identity'
import { useShellToast } from './toast-store'

/**
 * Switching persona and signing out, with what the persona menu needs to show: a label while one
 * runs, and an error if one fails. Both go through `resetIdentity` (switching through `signInAs`,
 * which also stores the new `me`) so nothing of the old person survives. A failure changes
 * nothing: the person stays who they were, and the error says what to do.
 *
 * Their `onSuccess` is on the mutation, not the call, because the reset remounts the shell and
 * this hook with it: a callback passed to `mutate` would be dropped, this one still runs.
 */
export function useIdentityActions() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const switching = useSwitchPersona({
    mutation: {
      onSuccess: (me) => {
        signInAs(queryClient, me)
        // signInAs has reset everything, the toast too, so this one is the only message left.
        useShellToast.getState().show(`Now viewing as ${me.givenName} ${me.familyName}.`, me.id)
        void navigate('/ask')
      },
    },
  })
  const signingOut = useEndSession({
    mutation: {
      onSuccess: () => {
        resetIdentity(queryClient)
        void navigate('/')
      },
    },
  })

  const target = switching.variables?.data.persona
  const targetFirstName = target ? personaFor(target).firstName : ''

  return {
    switchTo: (key: string) => {
      const persona = PERSONAS.find((p) => p.key === key)
      if (!persona) return
      signingOut.reset()
      switching.mutate({ data: { persona: persona.key as PersonaKey } })
    },
    signOut: () => {
      switching.reset()
      signingOut.mutate()
    },
    /** The switcher's label while something runs, such as "Switching to Marcus…". */
    busyLabel: switching.isPending
      ? `Switching to ${targetFirstName}…`
      : signingOut.isPending
        ? 'Signing out…'
        : undefined,
    /** What failed, and a way to do it again. Null when nothing has. */
    failure: switching.isError
      ? {
          message: `We couldn't switch to ${targetFirstName}.`,
          again: () => switching.mutate(switching.variables!),
        }
      : signingOut.isError
        ? { message: "We couldn't sign you out.", again: () => signingOut.mutate() }
        : null,
  }
}
