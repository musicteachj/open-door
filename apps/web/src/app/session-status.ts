import { useSyncExternalStore } from 'react'
import { registerReset } from '@/lib/identity'

// What the app knows about the session beyond /me itself. It is module state read through
// useSyncExternalStore, because the QueryClient's onUnauthorized runs outside React.
interface SessionStatus {
  /** How many times the identity has been reset. RequireSession uses it as the `key` of everything signed-in. */
  resetCount: number
  /**
   * When a request was last answered 401, or null. RequireSession counts it only if it is newer
   * than the last successful /me, so a 401 from an anonymous visit never outlives a later sign-in.
   */
  expiredAt: number | null
  /** Who the current identity was established with, or null until the first /me after a reset. */
  personId: string | null
}

let status: SessionStatus = { resetCount: 0, expiredAt: null, personId: null }
let lastResetAt = 0
const listeners = new Set<() => void>()

function update(next: SessionStatus) {
  status = next
  for (const listener of listeners) listener()
}

/**
 * A request got a 401: the session is gone. Wired to the QueryClient in main.tsx. A request that
 * started before the last reset belongs to the old identity, so its 401 says nothing about the
 * new one (a second switch answered 401 after the first rotated the session, for example).
 */
export function markExpired(requestStartedAt?: number) {
  if (requestStartedAt !== undefined && requestStartedAt <= lastResetAt) return
  update({ ...status, expiredAt: Date.now() })
}

/**
 * Starts a new identity: the next signed-in tree mounts fresh, and the expired flag is cleared.
 * resetIdentity runs it, so every switch, start, and sign-out remounts everything signed-in:
 * queryClient.clear() alone leaves mounted components watching queries that no longer exist.
 */
export function resetSessionStatus() {
  lastResetAt = Date.now()
  update({ resetCount: status.resetCount + 1, expiredAt: null, personId: null })
}

/** Remembers who this identity is, so a /me that names someone else can be recognized. */
export function rememberPerson(personId: string) {
  if (status.personId !== personId) update({ ...status, personId })
}

registerReset(resetSessionStatus)

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function useSessionStatus(): SessionStatus {
  return useSyncExternalStore(subscribe, () => status)
}
export function getSessionStatus(): SessionStatus {
  return status
}
