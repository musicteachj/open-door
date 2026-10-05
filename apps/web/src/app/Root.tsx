import { Outlet, ScrollRestoration } from 'react-router'

/** The top of every route. ScrollRestoration returns a list to where the visitor left it. */
export function Root() {
  return (
    <>
      <Outlet />
      <ScrollRestoration />
    </>
  )
}
