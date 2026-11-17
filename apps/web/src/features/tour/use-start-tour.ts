import { useStartSandbox } from '@/app/useStartSandbox'

/**
 * Starts a new sandbox as Priya and opens the guided tour at step 1: the landing's "Take the
 * 2-minute tour" and the menu's "Start the tour". It is the persona cards' own mutation (a new
 * sandbox, then `/ask`); the old sandbox, if there is one, stays until it expires.
 */
export function useStartTour() {
  const start = useStartSandbox({ tour: true })
  return {
    starting: start.isPending,
    /**
     * ANOTHER identity change is in flight: the tour waits. Its own start is not "blocked" (a
     * loading button stays enabled).
     */
    blocked: start.busy && !start.isPending,
    failed: start.isError,
    error: start.error,
    /** Forgets a failure, so the page shows one start error at a time. */
    dismissError: start.reset,
    /** `slot` is the empty `TurnstileSlot` under the control that was pressed. */
    start: (slot: HTMLElement | null) => {
      // The sandbox mutation refuses while any identity change is in flight (its own included).
      start.mutate({ data: { persona: 'priya' } }, slot)
    },
  }
}
