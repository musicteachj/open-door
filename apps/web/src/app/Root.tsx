import { Outlet } from 'react-router'
import { useScrollRestoration } from './use-scroll-restoration'

/** The top of every route. Scroll is kept by `useScrollRestoration`: Back returns to the list's place. */
export function Root() {
  useScrollRestoration()
  return <Outlet />
}
