import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useCallback, useRef } from 'react'
import { useNavigate } from 'react-router'
import {
  createSandbox,
  getCreateSandboxMutationKey,
  type CreateSandboxMutationError,
  type NewSandboxRequest,
  type SandboxCreated,
} from '@/api/generated'
import { useTourStore } from '@/features/tour/store'
import { announceSessionChange } from '@/lib/session-channel'
import { getTurnstileToken } from '@/lib/turnstile'
import { useIdentityBusy, useIdentityBusyNow } from './useIdentityBusy'
import { signInAs } from './useMe'

/** What a caller asks for: who to start as. The hook adds the Turnstile token. */
export type StartVariables = { data: Omit<NewSandboxRequest, 'turnstileToken'> }

/**
 * Starts a sandbox as a persona, signs in to it, and goes to the assistant. The landing page, the
 * tour's start, and the budget banner's "Start a new sandbox" all use it. It is one mutation, under
 * the generated create-sandbox key, and the mutation function first gets a fresh Turnstile token
 * (`getTurnstileToken`, rendered in the slot element the caller passes: the empty `TurnstileSlot`
 * under the control that was pressed), then calls the generated `createSandbox`. So `isPending`,
 * `variables`, `isError`, and the shared identity gate (`useIdentityBusy`, which watches that key)
 * cover the wait for the token as well as the request. When no token can be had (no slot, the
 * script won't load, the widget errors or never answers), the request goes with an empty token so
 * the API answers with its own refusal text: the web app holds none. A sandbox is a new identity:
 * `signInAs` resets everything of the old one, which remounts the page that called this, so the
 * success handler lives on the mutation and not on the call. With `{ tour: true }` the new sandbox
 * opens the guided tour at step 1 (the reset has cleared any earlier tour first). It refuses to
 * start while any identity change is in flight, its own included, checked at the press.
 */
export function useStartSandbox({ tour = false }: { tour?: boolean } = {}) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { busy: refused } = useIdentityBusy()
  const busyNow = useIdentityBusyNow()
  // The element the token's widget renders in. It travels in a ref, set at the press and read when
  // the mutation function starts, so the mutation's `variables` (kept in TanStack Query's cache)
  // hold plain data and never a DOM node. The identity gate allows one start at a time.
  const slotRef = useRef<HTMLElement | null>(null)
  const create = useMutation<SandboxCreated, CreateSandboxMutationError, StartVariables>({
    mutationKey: getCreateSandboxMutationKey(),
    mutationFn: async ({ data }) => {
      const slot = slotRef.current
      let turnstileToken = ''
      // No slot, no widget: it is never rendered anywhere else, away from the control.
      if (slot) {
        try {
          turnstileToken = await getTurnstileToken(slot)
        } catch {
          // Send nothing: the API's own 403 says so.
        }
      }
      return createSandbox({ ...data, turnstileToken })
    },
    onSuccess: ({ me }) => {
      signInAs(queryClient, me)
      announceSessionChange('start')
      if (tour) useTourStore.getState().begin()
      void navigate('/ask')
    },
  })
  const { mutateAsync: createAsync, mutate: createMutate } = create

  // Refused, not left hanging: a caller that awaits gets an error it can show or ignore. Every
  // control that starts a sandbox is disabled while busy, so a refusal only guards a press that
  // lands before the page has re-rendered.
  const startAsync = useCallback(
    async (variables: StartVariables, slot: HTMLElement | null) => {
      if (busyNow()) throw new Error('An identity change is already in progress.')
      slotRef.current = slot
      return createAsync(variables)
    },
    [busyNow, createAsync],
  )
  const start = useCallback(
    (variables: StartVariables, slot: HTMLElement | null) => {
      if (busyNow()) return
      slotRef.current = slot
      createMutate(variables)
    },
    [busyNow, createMutate],
  )
  return {
    ...create,
    /** The only way to start: `mutate(variables, slotElement)`. */
    mutate: start,
    mutateAsync: startAsync,
    busy: refused,
  }
}
