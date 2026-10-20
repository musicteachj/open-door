// Says something to a screen reader without showing it. A live region that is inserted into the
// page in the same instant as its text is often not announced, because a screen reader has to see
// a region first and a change in it after. So this keeps one pair of hidden live regions (polite
// and assertive) in the page for good (the way react-aria's announcer is), and only their text
// changes. `installAnnouncer` makes them at app start, and the first `announce` makes them if that
// never ran. A component that appears with news of its own, such as the panel for a
// crisis, calls `announce` instead of carrying a region that arrives with it.

type Politeness = 'polite' | 'assertive'

/** The text is set this long after the region is cleared, so a repeat of it is read again. */
export const ANNOUNCE_DELAY_MS = 50

/** The text is taken out again this long after it is set, so nothing is left to find by browsing. */
const CLEAR_AFTER_MS = 7000

type Announcer = {
  root: HTMLElement
  regions: Record<Politeness, HTMLElement>
  timers: Record<Politeness, ReturnType<typeof setTimeout> | undefined>
}

let announcer: Announcer | null = null

function region(politeness: Politeness): HTMLElement {
  // role="log", not "status" or "alert": those roles would show up in a page's own queries for
  // its status messages and alerts, and these regions are not part of any one component.
  const element = document.createElement('div')
  element.setAttribute('role', 'log')
  element.setAttribute('aria-live', politeness)
  element.setAttribute('aria-relevant', 'additions text')
  return element
}

function ensureAnnouncer(): Announcer {
  if (announcer?.root.isConnected) return announcer
  const root = document.createElement('div')
  root.setAttribute('data-slot', 'announcer')
  root.className = 'sr-only'
  const regions = { polite: region('polite'), assertive: region('assertive') }
  root.append(regions.polite, regions.assertive)
  document.body.append(root)
  announcer = { root, regions, timers: { polite: undefined, assertive: undefined } }
  return announcer
}

/**
 * Puts the live regions in the page now. The app calls this once at start, before its first
 * render, so the regions are in the page long before anything is announced (a region made in the
 * same moment as its first text is the case screen readers miss). `announce` still makes them
 * itself if nothing installed them, as a fallback. Safe to call again.
 */
export function installAnnouncer(): void {
  ensureAnnouncer()
}

/**
 * Announces `text`. The region is cleared at once and the text is set after a short delay, so a
 * message that repeats is read again, and the last of two quick messages is the one said.
 * `assertive` interrupts, and is for a crisis. Everything else is `polite`.
 */
export function announce(text: string, politeness: Politeness = 'polite'): void {
  const { regions, timers } = ensureAnnouncer()
  const target = regions[politeness]
  clearTimeout(timers[politeness])
  target.textContent = ''
  timers[politeness] = setTimeout(() => {
    target.textContent = text
    timers[politeness] = setTimeout(() => {
      target.textContent = ''
    }, CLEAR_AFTER_MS)
  }, ANNOUNCE_DELAY_MS)
}

/** Removes the regions and any waiting timers. For tests, so one test's regions never reach the next. */
export function resetAnnouncer(): void {
  if (!announcer) return
  clearTimeout(announcer.timers.polite)
  clearTimeout(announcer.timers.assertive)
  announcer.root.remove()
  announcer = null
}
