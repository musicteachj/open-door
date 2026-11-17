import { Outlet } from 'react-router'
import { useScrollRestoration } from './use-scroll-restoration'
import { useSessionChannel } from './use-session-channel'

/** The top of every route. Scroll is kept by `useScrollRestoration`: Back returns to the list's place. Another tab's session change refetches /me. */
export function Root() {
  useScrollRestoration()
  useSessionChannel()
  return <Outlet />
}
