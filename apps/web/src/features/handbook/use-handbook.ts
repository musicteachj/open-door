import { useGetHandbook } from '@/api/generated'

/**
 * The handbook's version, chapter names, and every section of the sandbox's pinned version, each
 * with whether it applies to the signed-in person (worked out on the server). The list is the
 * page: a failure goes to the route's error boundary, which shows "Something went wrong" inside
 * the shell.
 */
export function useHandbook() {
  return useGetHandbook({ query: { throwOnError: true } })
}
