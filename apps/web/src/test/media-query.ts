import { vi } from 'vitest'

/**
 * Stands in for `window.matchMedia`: every query answers `matches`, until `set` changes it and
 * tells the listeners. jsdom has no matchMedia, so a test that needs a narrow window uses this.
 * Undo it with `vi.unstubAllGlobals()`.
 */
export function stubMediaQuery(initial: boolean) {
  let matches = initial
  const listeners = new Set<() => void>()
  const asked: string[] = []
  let subscribed = 0
  vi.stubGlobal('matchMedia', (query: string) => {
    asked.push(query)
    return {
      get matches() {
        return matches
      },
      media: query,
      addEventListener: (_type: string, listener: () => void) => {
        subscribed++
        listeners.add(listener)
      },
      removeEventListener: (_type: string, listener: () => void) => listeners.delete(listener),
    }
  })
  return {
    set(next: boolean) {
      matches = next
      for (const listener of [...listeners]) listener()
    },
    listeners: () => listeners.size,
    /** How many times a listener was added, however many were removed since. */
    subscribed: () => subscribed,
    queries: () => asked,
  }
}
