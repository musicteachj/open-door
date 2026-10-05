import type { QueryClient } from '@tanstack/react-query'
import { getGetMeQueryKey, useGetMe, type Me } from '@/api/generated'
import { resetIdentity } from '@/lib/identity'
import { rememberPerson } from './session-status'

/** Who is signed in. The landing page and the session guard share this one query. */
export function useMe() {
  return useGetMe()
}

/**
 * A start or a switch has answered with the new person. Resets everything of the old identity,
 * then seeds /me so the signed-in pages have the new person at once. Seeding is why the remount
 * in RequireSession matters: with data already there, nothing shows a loading state, so only the
 * reset count's `key` stops a mounted component from still watching the old person's query.
 */
export function signInAs(queryClient: QueryClient, me: Me) {
  resetIdentity(queryClient)
  queryClient.setQueryData(getGetMeQueryKey(), me)
  rememberPerson(me.id)
}
