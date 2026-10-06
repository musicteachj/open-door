import { useReducer } from 'react'

// Whether the person closed the expiry banner, kept in sessionStorage so it survives a reload but
// not the tab. The key holds the sandbox's expiry, so a new sandbox (a new expiry) shows the
// banner again. See docs/DATA-INVENTORY.md.
export const dismissalKey = (tenantExpiresAt: string) =>
  `od.expiryBannerDismissed.${tenantExpiresAt}`

function read(key: string): boolean {
  try {
    return window.sessionStorage.getItem(key) === '1'
  } catch {
    // Storage can be blocked. The banner then comes back on each load, which is harmless.
    return false
  }
}

function write(key: string) {
  try {
    window.sessionStorage.setItem(key, '1')
  } catch {
    // Same: the dismissal then lasts only until the page reloads.
  }
}

/** `[dismissed, dismiss]` for this sandbox's banner. */
export function useExpiryBannerDismissal(tenantExpiresAt: string): [boolean, () => void] {
  const [, rerender] = useReducer((count: number) => count + 1, 0)
  const key = dismissalKey(tenantExpiresAt)
  return [
    read(key),
    () => {
      write(key)
      rerender()
    },
  ]
}
