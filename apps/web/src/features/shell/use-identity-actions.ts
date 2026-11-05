import { useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'
import { useNavigate } from 'react-router'
import { useEndSession, useSwitchPersona, type PersonaKey } from '@/api/generated'
import { useIdentityBusy, useIdentityBusyNow } from '@/app/useIdentityBusy'
import { signInAs } from '@/app/useMe'
import { PERSONAS, personaFor } from '@/features/personas/personas'
import { resetIdentity } from '@/lib/identity'
import { useTourStore } from '@/features/tour/store'
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
  const { starting } = useIdentityBusy()
  const busyNow = useIdentityBusyNow()
  // Where a successful switch goes. A ref, since the reset remounts the shell and the mutation's
  // `onSuccess` is the callback that still runs.
  const destination = useRef('/ask')

  const switching = useSwitchPersona({
    mutation: {
      onSuccess: (me) => {
        signInAs(queryClient, me, 'switch')
        // signInAs has reset everything, the toast too, so this one is the only message left.
        useShellToast.getState().show(`Now viewing as ${me.givenName} ${me.familyName}.`, me.id)
        void navigate(destination.current)
      },
      // The shell's Retry runs the same switch again; it must not land on a tour page.
      onError: () => {
        destination.current = '/ask'
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
    /**
     * The tour's own switches pass `{ tour: true }`. A visitor's own switch leaves the tour (the
     * step is kept, so the menu offers Resume), and the tour never fights them for the persona.
     * A switch lands on `/ask` unless `to` names another page (the tour passes its step's page, so
     * it does not flash `/ask` and fetch its data first). Returns whether the switch started
     * (false when another identity change is in flight).
     */
    switchTo: (key: string, options: { tour?: boolean; to?: string } = {}): boolean => {
      const persona = PERSONAS.find((p) => p.key === key)
      if (!persona) return false
      // Two identity changes in flight would race for the session cookies: not both at once.
      if (busyNow()) return false
      signingOut.reset()
      destination.current = options.to ?? '/ask'
      switching.mutate({ data: { persona: persona.key as PersonaKey } })
      if (!options.tour && useTourStore.getState().active) useTourStore.getState().leave()
      return true
    },
    /** Returns whether the sign-out started (false when another identity change is in flight). */
    signOut: (): boolean => {
      if (busyNow()) return false
      switching.reset()
      signingOut.mutate()
      return true
    },
    /** The switcher's label while something runs, such as "Switching to Marcus…". */
    busyLabel: switching.isPending
      ? `Switching to ${targetFirstName}…`
      : signingOut.isPending
        ? 'Signing out…'
        : starting
          ? 'Starting a new sandbox…'
          : undefined,
    /** Forgets a shown switch or sign-out failure, so a new identity action shows one error. */
    clearFailure: () => {
      switching.reset()
      signingOut.reset()
    },
    /** What failed, and a way to do it again. Null when nothing has. */
    failure: switching.isError
      ? {
          message: `We couldn't switch to ${targetFirstName}.`,
          again: () => {
            if (!busyNow()) switching.mutate(switching.variables!)
          },
        }
      : signingOut.isError
        ? {
            message: "We couldn't sign you out.",
            again: () => {
              if (!busyNow()) signingOut.mutate()
            },
          }
        : null,
  }
}
