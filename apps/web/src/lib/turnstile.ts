// Cloudflare Turnstile, loaded only when a visitor presses a control that starts a sandbox, never on
// page load. One widget is rendered per start in a slot under the control, executed at once, and
// removed when it answers, so every start carries a fresh single-use token. In its
// `interaction-only` mode the widget stays invisible unless Cloudflare needs a click, and then its
// checkbox appears in the slot. Source: developers.cloudflare.com/turnstile, read 2026-11-11.

export const TURNSTILE_SCRIPT_URL =
  'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'

/** The action the API's check expects (`start-sandbox`). */
const ACTION = 'start-sandbox'

/**
 * Cloudflare's documented always-pass test key. An empty site key means the page was not served by
 * the API (Vite's dev server and preview), which writes the real key into the page. This is safe:
 * a production API never writes an empty key, and if it did, the dummy tokens this key produces
 * would be refused by the real secret, so the start still fails closed.
 */
const TEST_SITE_KEY = '1x00000000000000000000AA'

/** How long Cloudflare's script may take to load before the start goes on without a token. */
export const SCRIPT_TIMEOUT_MS = 10_000

/**
 * How long a widget may take to answer. Long enough for a person to find and solve an interactive
 * checkbox (the widget has its own shorter callbacks for most failures); it only bounds a widget
 * that never calls back at all, so the start can't hang until a reload.
 */
export const TOKEN_TIMEOUT_MS = 120_000

type TurnstileOptions = {
  sitekey: string
  action: string
  execution: 'execute' | 'render'
  appearance: 'always' | 'execute' | 'interaction-only'
  callback: (token: string) => void
  'error-callback': (code?: string) => unknown
  'expired-callback': () => void
  'timeout-callback': () => void
}

export type TurnstileApi = {
  render: (container: HTMLElement, options: TurnstileOptions) => string | undefined
  execute: (container: HTMLElement | string) => void
  reset: (widgetId?: string) => void
  remove: (widgetId?: string) => void
}

declare global {
  interface Window {
    turnstile?: TurnstileApi
  }
}

let scriptPromise: Promise<TurnstileApi> | null = null
// Set when a load gave up on a script that may still finish and define the API.
let timedOut = false

function readSiteKey(): string {
  const content = document.querySelector<HTMLMetaElement>(
    'meta[name="turnstile-site-key"]',
  )?.content
  return content?.trim() ? content.trim() : TEST_SITE_KEY
}

/**
 * Loads Cloudflare's script once. A failure, or no answer within `SCRIPT_TIMEOUT_MS`, rejects and
 * is forgotten (the script element is removed), so a later press tries again. The script is not proxied or cached by us: Cloudflare asks that it come from them.
 */
export function loadTurnstile(): Promise<TurnstileApi> {
  if (scriptPromise) return scriptPromise
  // A script that outlived its timeout may still have finished: use it rather than load a second
  // copy, which Cloudflare's runtime doesn't expect.
  if (timedOut && window.turnstile) return Promise.resolve(window.turnstile)
  const loading = new Promise<TurnstileApi>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = TURNSTILE_SCRIPT_URL
    script.async = true
    const timer = setTimeout(() => {
      timedOut = true
      script.remove()
      reject(new Error('The Turnstile script took too long to load.'))
    }, SCRIPT_TIMEOUT_MS)
    script.addEventListener('load', () => {
      clearTimeout(timer)
      if (window.turnstile) {
        resolve(window.turnstile)
      } else {
        // Removed too, or each retry would add another copy to the page.
        script.remove()
        reject(new Error('The Turnstile script loaded without its API.'))
      }
    })
    script.addEventListener('error', () => {
      clearTimeout(timer)
      script.remove()
      reject(new Error('The Turnstile script could not be loaded.'))
    })
    document.head.append(script)
  })
  scriptPromise = loading
  loading.catch(() => {
    if (scriptPromise === loading) scriptPromise = null
  })
  return loading
}

/**
 * A fresh token for one sandbox start. Renders one widget in `container`, executes it, and resolves
 * with the token; rejects on an error, a timeout, an expiry, or no answer at all within
 * `TOKEN_TIMEOUT_MS`. The widget is always removed after.
 */
export async function getTurnstileToken(container: HTMLElement): Promise<string> {
  const turnstile = await loadTurnstile()
  return new Promise<string>((resolve, reject) => {
    let widgetId: string | undefined
    let settled = false
    const timer = setTimeout(
      () => finish(() => reject(new Error('The Turnstile check did not answer.'))),
      TOKEN_TIMEOUT_MS,
    )
    const finish = (settle: () => void) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      try {
        if (widgetId !== undefined) turnstile.remove(widgetId)
      } catch {
        // A widget that is already gone is the state wanted.
      }
      settle()
    }
    try {
      widgetId = turnstile.render(container, {
        sitekey: readSiteKey(),
        action: ACTION,
        execution: 'execute',
        appearance: 'interaction-only',
        callback: (token) => finish(() => resolve(token)),
        'error-callback': (code) =>
          finish(() => reject(new Error(`The Turnstile check failed (${code ?? 'unknown'}).`))),
        'expired-callback': () => finish(() => reject(new Error('The Turnstile token expired.'))),
        'timeout-callback': () => finish(() => reject(new Error('The Turnstile check timed out.'))),
      })
      turnstile.execute(widgetId ?? container)
    } catch (error) {
      finish(() =>
        reject(error instanceof Error ? error : new Error('The Turnstile check failed.')),
      )
    }
  })
}

/** For tests: forget the loaded script. */
export function resetTurnstileForTests(): void {
  scriptPromise = null
  timedOut = false
}
