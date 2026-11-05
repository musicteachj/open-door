/**
 * An opaque, per-tab stand-in for a turn's server ID, safe to put in the DOM (no ID shows in the
 * page). The first call for an ID, from any caller, assigns the next number, so the views and the
 * tour always get the same key for the same ID. Never stored and never sent anywhere.
 */
const keys = new Map<string, string>()

export function turnKey(turnId: string): string {
  let key = keys.get(turnId)
  if (key === undefined) {
    key = `t${keys.size + 1}`
    keys.set(turnId, key)
  }
  return key
}
