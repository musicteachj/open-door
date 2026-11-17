// "Back to the demo" returns the visitor to where they came from inside Open Door (screen 16's
// build decisions), and to the landing when they came from outside or opened the page directly.
// Every link into the page carries the place it was pressed on in the router's state; browser
// history keeps that state across a reload.

export const WALKTHROUGH_PATH = '/walkthrough'

type WalkthroughState = { from: string }

/** The router state a link into the walkthrough carries. */
export function walkthroughState(location: {
  pathname: string
  search: string
  hash: string
}): WalkthroughState {
  return { from: `${location.pathname}${location.search}${location.hash}` }
}

// A backslash, whitespace, or a control character never appears in a path the router gives (it
// encodes them), and URL parsing reads a backslash as `/` and drops tabs and newlines, so
// `/\t/host` would become `//host`.
// Control characters are what it looks for.
// oxlint-disable-next-line no-control-regex
const UNSAFE = /[\\\s\u0000-\u001f\u007f]/

/**
 * Where "Back to the demo" goes. Only an in-app path is followed: one starting with a single `/`
 * (`//host` would leave the site), and never the walkthrough itself. Anything else is the landing.
 */
export function backTarget(state: unknown): string {
  if (typeof state !== 'object' || state === null || !('from' in state)) return '/'
  const { from } = state
  if (typeof from !== 'string' || !from.startsWith('/') || from.startsWith('//')) return '/'
  if (UNSAFE.test(from)) return '/'
  // The router matches decoded paths whatever their case, so `/Walkthrough` and `/walk%74hrough`
  // are the page too. A path that doesn't decode is no page of the app's.
  let path: string
  try {
    path = decodeURIComponent(from.split(/[?#]/, 1)[0]).toLowerCase()
  } catch {
    return '/'
  }
  if (path === WALKTHROUGH_PATH || path.startsWith(`${WALKTHROUGH_PATH}/`)) return '/'
  return from
}
