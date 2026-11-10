import { useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import { useNavigate } from 'react-router'
import { useCreateSandbox } from '@/api/generated'
import { useTourStore } from '@/features/tour/store'
import { announceSessionChange } from '@/lib/session-channel'
import { useIdentityBusy, useIdentityBusyNow } from './useIdentityBusy'
import { signInAs } from './useMe'

/**
 * Starts a sandbox as a persona, signs in to it, and goes to the assistant. The landing page and
 * the budget banner's "Start a new sandbox" both use it. It is the generated mutation, so a page
 * reads `isPending`, `isError`, and `variables` from it as from any other. A sandbox is a new
 * identity: `signInAs` resets everything of the old one, which remounts the page that called this,
 * so the success handler lives on the mutation and not on the call. With `{ tour: true }` the new
 * sandbox opens the guided tour at step 1 (the reset has cleared any earlier tour first). It
 * refuses to start while any identity change is in flight (`useIdentityBusy`): their answers set
 * the session cookies, so the later one would leave the browser as one person and the screen
 * another.
 */
export function useStartSandbox({ tour = false }: { tour?: boolean } = {}) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { busy: refused } = useIdentityBusy()
  const busyNow = useIdentityBusyNow()
  const create = useCreateSandbox({
    mutation: {
      onSuccess: ({ me }) => {
        signInAs(queryClient, me)
        announceSessionChange('start')
        if (tour) useTourStore.getState().begin()
        void navigate('/ask')
      },
    },
  })
  const { mutate, mutateAsync } = create
  // A refused `mutate` is a no-op: every control that starts a sandbox is disabled while busy, so
  // this only guards a press that lands before the page has re-rendered.
  const guardedMutate = useCallback(
    (...args: Parameters<typeof mutate>) => {
      if (!busyNow()) mutate(...args)
    },
    [busyNow, mutate],
  ) as typeof mutate
  // Refused, not left hanging: a caller that awaits gets an error it can show or ignore.
  const guardedMutateAsync = useCallback(
    (...args: Parameters<typeof mutateAsync>) =>
      busyNow()
        ? Promise.reject(new Error('An identity change is already in progress.'))
        : mutateAsync(...args),
    [busyNow, mutateAsync],
  ) as typeof mutateAsync
  return { ...create, mutate: guardedMutate, mutateAsync: guardedMutateAsync, busy: refused }
}
