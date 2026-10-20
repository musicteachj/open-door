import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { useCreateSandbox } from '@/api/generated'
import { signInAs } from './useMe'

/**
 * Starts a sandbox as a persona, signs in to it, and goes to the assistant. The landing page and
 * the budget banner's "Start a new sandbox" both use it. It is the generated mutation, so a page
 * reads `isPending`, `isError`, and `variables` from it as from any other. A sandbox is a new
 * identity: `signInAs` resets everything of the old one, which remounts the page that called this,
 * so the success handler lives on the mutation and not on the call.
 */
export function useStartSandbox() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  return useCreateSandbox({
    mutation: {
      onSuccess: ({ me }) => {
        signInAs(queryClient, me)
        void navigate('/ask')
      },
    },
  })
}
