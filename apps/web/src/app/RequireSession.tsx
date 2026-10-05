import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Navigate, Outlet } from 'react-router'
import { ApiError } from '@/lib/api-fetch'
import { SessionExpired, SomethingWentWrong } from './placeholders'
import { rememberPerson, useSessionStatus } from './session-status'
import { signInAs, useMe } from './useMe'

/**
 * The layout route for every signed-in page. It loads /me before anything renders.
 *
 * Everything under it, the shell included, is keyed by the reset count, so a persona switch or a
 * sign-out unmounts it all and nothing keeps showing the old person.
 */
export function RequireSession() {
  const { resetCount } = useSessionStatus()
  return <Session key={resetCount} />
}

function Session() {
  const me = useMe()
  const queryClient = useQueryClient()
  const { expiredAt, personId } = useSessionStatus()
  const unauthorized = me.error instanceof ApiError && me.error.status === 401

  // Another tab changed who is signed in (a switch, or a new sandbox) and /me now names someone
  // else. This is the one place that notices: reset as a switch here would, which remounts this
  // tree with only the new person's data. Until then, render nothing of the old person's pages.
  const changed = me.data !== undefined && personId !== null && me.data.id !== personId
  const person = me.data
  useEffect(() => {
    if (!person) return
    if (changed) signInAs(queryClient, person)
    else if (personId === null) rememberPerson(person.id)
  }, [person, changed, personId, queryClient])

  // A 401 after /me has succeeded: the sandbox reset, usually at its 24 hours.
  const expired = expiredAt !== null && expiredAt > me.dataUpdatedAt
  if (me.data && (expired || unauthorized)) return <SessionExpired />
  // A 401 on the first load: nobody is signed in.
  if (unauthorized) return <Navigate to="/" replace />
  // Any other failure of the first load: the shell itself cannot load.
  if (me.isError && !me.data) return <SomethingWentWrong onRetry={() => void me.refetch()} />
  if (!me.data) return <output>Loading…</output>
  if (changed) return null
  return <Outlet />
}
