import type { QueryClient } from '@tanstack/react-query'

// Everything that remembers who the user is registers a reset here, so nothing of the old identity
// survives a persona switch or a sign-out. The Zustand stores register themselves.
/** Why the identity changed, when a reset cares: `switch` is a persona switch landing. */
export type ResetReason = 'switch'

const resets = new Set<(reason?: ResetReason) => void>()

/** Adds a reset to run on every identity change. Returns a function that removes it. */
export function registerReset(reset: (reason?: ResetReason) => void): () => void {
  resets.add(reset)
  return () => {
    resets.delete(reset)
  }
}

/**
 * Clears the query cache, then runs every registered reset. If a reset throws, the others still
 * run, and the first error is thrown at the end.
 */
export function resetIdentity(queryClient: QueryClient, reason?: ResetReason): void {
  queryClient.clear()
  const errors: unknown[] = []
  for (const reset of [...resets]) {
    try {
      reset(reason)
    } catch (error) {
      errors.push(error)
    }
  }
  if (errors.length > 0) throw errors[0]
}
