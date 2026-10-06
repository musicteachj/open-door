import { useQueryErrorResetBoundary } from '@tanstack/react-query'
import { isRouteErrorResponse, useLocation, useNavigate, useRouteError } from 'react-router'
import { isNotFound, requestIdOf } from './errors'
import { NotFound, SomethingWentWrong } from './pages'

/**
 * The route `errorElement` for everything signed-in. A page lets a failed query throw
 * (`throwOnError`), and this shows it where the page would have been, so the shell stays:
 * not found for a 404, "Something went wrong" for anything else. Retry clears the failed queries
 * and replaces the location with itself, which re-renders the page and so repeats what failed.
 */
export function RouteError() {
  const error = useRouteError()
  const { reset } = useQueryErrorResetBoundary()
  const navigate = useNavigate()
  const location = useLocation()

  if (isNotFound(error) || (isRouteErrorResponse(error) && error.status === 404)) {
    return <NotFound />
  }
  return (
    <SomethingWentWrong
      requestId={requestIdOf(error)}
      onRetry={() => {
        reset()
        // The boundary clears when the location changes, so a replace to the same URL re-renders
        // the page. (revalidate() does nothing without loaders: the pages load through queries.)
        void navigate(`${location.pathname}${location.search}${location.hash}`, {
          replace: true,
          state: location.state,
          preventScrollReset: true,
        })
      }}
    />
  )
}

/**
 * The root route's `errorElement`: a render error on the landing page or any page outside the
 * session guard. There is no shell to keep, so the page fills the window, and Retry reloads it.
 */
export function RootError() {
  return (
    <SomethingWentWrong
      outsideShell
      requestId={requestIdOf(useRouteError())}
      onRetry={() => window.location.reload()}
    />
  )
}
