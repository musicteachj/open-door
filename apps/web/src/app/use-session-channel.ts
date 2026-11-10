import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { getGetMeQueryKey } from '@/api/generated'
import { listenForSessionChanges } from '@/lib/session-channel'

/**
 * Another tab of this browser switched persona, signed out, or started a sandbox: refetch `/me`
 * at once, once per message. A tab whose person changed resets (RequireSession notices that /me
 * names someone else), and one whose session ended shows "This sandbox has reset", so neither
 * keeps showing what it loaded, such as HR's view of someone's private details, until the person
 * happens to focus it. Mounted once, at the app's root.
 */
export function useSessionChannel() {
  const queryClient = useQueryClient()
  useEffect(
    () =>
      listenForSessionChanges(() => {
        void queryClient.invalidateQueries({ queryKey: getGetMeQueryKey() })
      }),
    [queryClient],
  )
}
