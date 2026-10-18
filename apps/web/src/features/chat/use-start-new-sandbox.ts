import { useMe } from '@/app/useMe'
import { useStartSandbox } from '@/app/useStartSandbox'

/**
 * "Start a new sandbox", from the budget banner: the landing page's own call, as the person who is
 * signed in now. A new sandbox starts with a fresh budget, so the page that comes after the reset
 * is a new sandbox's /ask.
 */
export function useStartNewSandbox() {
  const { data: me } = useMe()
  const start = useStartSandbox()
  return {
    startNewSandbox: () => {
      if (me && !start.isPending) start.mutate({ data: { persona: me.personaKey } })
    },
    failed: start.isError,
  }
}
