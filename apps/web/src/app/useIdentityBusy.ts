import { useIsMutating, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import {
  getCreateSandboxMutationKey,
  getEndSessionMutationKey,
  getSwitchPersonaMutationKey,
} from '@/api/generated'

// The one list of identity changes: both gates below read it, so a new one is added once.
const IDENTITY_MUTATION_KEYS = [
  getSwitchPersonaMutationKey(),
  getCreateSandboxMutationKey(),
  getEndSessionMutationKey(),
]

/**
 * Whether an identity change is in flight anywhere in the app: a persona switch, a sign out, or a
 * sandbox start. They must never overlap: each one's answer sets the session cookies and then
 * resets the page for a new person, so whichever answers last would leave the browser's session and
 * the screen on different people.
 */
export function useIdentityBusy() {
  const [switchKey, startKey, signOutKey] = IDENTITY_MUTATION_KEYS
  const switching = useIsMutating({ mutationKey: switchKey }) > 0
  const starting = useIsMutating({ mutationKey: startKey }) > 0
  const signingOut = useIsMutating({ mutationKey: signOutKey }) > 0
  // The one gate: every identity entry point and every control for one reads `busy`.
  return { switching, starting, signingOut, busy: switching || starting || signingOut }
}

/**
 * The same gate, read at call time. `busy` above is from the last render, so two identity actions
 * started in the same tick would both pass it; this asks the mutation cache, which already holds
 * the first one. Every identity entry point calls it before it starts anything.
 */
export function useIdentityBusyNow() {
  const queryClient = useQueryClient()
  return useCallback(
    () => IDENTITY_MUTATION_KEYS.some((mutationKey) => queryClient.isMutating({ mutationKey }) > 0),
    [queryClient],
  )
}
