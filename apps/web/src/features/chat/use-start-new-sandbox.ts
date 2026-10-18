import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { useCreateSandbox } from '@/api/generated'
import { signInAs, useMe } from '@/app/useMe'

/**
 * "Start a new sandbox", from the budget banner: the same call the landing page makes, as the
 * person who is signed in now. A new sandbox starts with a fresh budget, so the page that comes
 * after the reset is a new sandbox's /ask.
 */
export function useStartNewSandbox() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { data: me } = useMe()
  const start = useCreateSandbox({
    mutation: {
      onSuccess: ({ me: person }) => {
        signInAs(queryClient, person)
        void navigate('/ask')
      },
    },
  })
  return {
    startNewSandbox: () => {
      if (me && !start.isPending) start.mutate({ data: { persona: me.personaKey } })
    },
    failed: start.isError,
  }
}
