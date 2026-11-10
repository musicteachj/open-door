/**
 * Tells the other tabs of this browser that the session changed under them: a persona switch, a
 * sign-out, or a new sandbox. All of a browser's tabs share one session cookie, so when one tab
 * changes who is signed in, every other tab is showing a person who no longer is (HR's private
 * details, for one). A tab that hears the message refetches `/me`, which resets it.
 *
 * The message is only `{ kind, from }`: what happened and which tab said so. It never carries a
 * token, a name, or an ID of a person, so what it reveals to any other script on this origin is
 * nothing it could not already see. `from` is a random ID for this tab, made when the page loads,
 * so the tab that announced ignores its own message.
 *
 * Where `BroadcastChannel` is missing (or the browser refuses to open one), announcing and
 * listening do nothing, and a tab learns of the change the way it did before: on its next fetch.
 */

export const SESSION_CHANNEL_NAME = 'od.session'

export type SessionChangeKind = 'switch' | 'sign-out' | 'start'
const KINDS: readonly string[] = ['switch', 'sign-out', 'start'] satisfies SessionChangeKind[]

/** A random ID for this tab, for the life of the page. Not a secret and never stored. */
export const TAB_ID: string =
  typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`

function openChannel(): BroadcastChannel | null {
  if (typeof BroadcastChannel === 'undefined') return null
  try {
    return new BroadcastChannel(SESSION_CHANNEL_NAME)
  } catch {
    return null
  }
}

/** Posts that this tab changed the session. Call it once the server has answered. */
export function announceSessionChange(kind: SessionChangeKind): void {
  // Opened and closed per message: a change is rare, and a closed channel holds nothing. The
  // message is already queued for the other tabs when `close` runs.
  const channel = openChannel()
  if (!channel) return
  channel.postMessage({ kind, from: TAB_ID })
  channel.close()
}

/**
 * Calls `onChange` for each change another tab announces. Returns the function that stops it.
 * Messages from this tab, and anything that isn't `{ kind, from }` from this app, are ignored.
 */
export function listenForSessionChanges(onChange: (kind: SessionChangeKind) => void): () => void {
  const channel = openChannel()
  if (!channel) return () => {}
  channel.onmessage = (event: MessageEvent) => {
    const data: unknown = event.data
    if (typeof data !== 'object' || data === null) return
    const { kind, from } = data as { kind?: unknown; from?: unknown }
    if (typeof from !== 'string' || from === TAB_ID) return
    if (typeof kind !== 'string' || !KINDS.includes(kind)) return
    onChange(kind as SessionChangeKind)
  }
  return () => channel.close()
}
