import {
  expect,
  test as base,
  type Browser,
  type BrowserContext,
  type BrowserContextOptions,
  type ConsoleMessage,
  type Page,
} from '@playwright/test'

// Every browser test imports `test` and `expect` from here, not from '@playwright/test' (oxlint
// refuses the direct import in spec files). The extended `test` fails any test during which the
// page reported a Content Security Policy violation. Against the production image
// (`E2E_TARGET=image`) the page carries the real CSP, so a library that injects a style or script
// without the page's nonce fails the test that loaded it. Against the Vite preview there is no
// CSP, so nothing is ever reported: the guard costs nothing there.
//
// Two sources, because each can miss: the `securitypolicyviolation` event (fired in the page, on
// every frame of every page in the context) and the console error the browser logs for the same
// block ("Refused to apply inline style ...").

// No browser test reaches Cloudflare. Every page of every context gets Cloudflare's Turnstile script
// from a local fake (`fakeTurnstile`), which answers a start with the documented dummy token the API
// accepts for the test keys. The real widget's iframe never runs under the CSP in these tests; the
// live check through the production image covers it (Stage 9).

const BINDING = '__reportCspViolation'
const CONSOLE_CSP = /content security policy|content-security-policy/i

type Violation = { directive: string; blocked: string; source: string }

/**
 * Starts listening for CSP violations in every page of this context, now and later. Returns a
 * function that gives the violations seen so far, as readable lines. The `context` fixture and
 * `guardedContext` use it.
 */
export async function watchCsp(context: BrowserContext): Promise<() => string[]> {
  const seen: string[] = []
  await context.exposeBinding(BINDING, (_source, violation: Violation) => {
    seen.push(
      `${violation.directive} blocked ${violation.blocked || '(inline)'} at ${violation.source}`,
    )
  })
  await context.addInitScript((binding) => {
    document.addEventListener('securitypolicyviolation', (event) => {
      const report = (window as unknown as Record<string, (v: Violation) => void>)[binding]
      report?.({
        directive: event.effectiveDirective,
        blocked: event.blockedURI,
        source: `${event.sourceFile || location.href}:${event.lineNumber}`,
      })
    })
  }, BINDING)
  const onConsole = (message: ConsoleMessage) => {
    if (message.type() === 'error' && CONSOLE_CSP.test(message.text())) {
      seen.push(`console: ${message.text()}`)
    }
  }
  context.on('console', onConsole)
  return () => seen
}

const TURNSTILE_SCRIPT = 'https://challenges.cloudflare.com/turnstile/v0/api.js*'

// The fake widget: render, execute, reset, and remove, as the app calls them. `execute` answers
// asynchronously with the dummy token, or with the error callback when the test set
// `window.__turnstileFail` (it stands in for the always-fail test key), or never when the test set
// `window.__turnstileHold` (the answer is awaited, so the stand-in box stays on the page). With
// `window.__turnstileStandIn`, `render` draws a visible box in the slot where Cloudflare's checkbox
// would appear (the size of the real widget, 300 by 65 px), for the capture report.
const FAKE_TURNSTILE = `(function () {
  var count = 0;
  var widgets = {};
  window.turnstile = {
    render: function (container, options) {
      count += 1;
      var id = 'fake-' + count;
      widgets[id] = { options: options, container: container };
      if (window.__turnstileStandIn) {
        var box = document.createElement('div');
        box.setAttribute('data-fake-turnstile', id);
        box.textContent = 'Cloudflare check';
        box.style.cssText = 'box-sizing:border-box;width:300px;max-width:100%;height:65px;border:1px dashed #888;display:flex;align-items:center;justify-content:center;font:14px sans-serif';
        container.appendChild(box);
      }
      return id;
    },
    execute: function (target) {
      var widget = widgets[target];
      if (!widget || window.__turnstileHold) return;
      setTimeout(function () {
        if (!widgets[target]) return;
        if (window.__turnstileFail) widget.options['error-callback']('300030');
        else widget.options.callback('XXXX.DUMMY.TOKEN.XXXX');
      }, 0);
    },
    reset: function () {},
    remove: function (id) {
      var widget = widgets[id];
      if (widget) widget.container.replaceChildren();
      delete widgets[id];
    }
  };
})();`

const turnstileRequests = new WeakMap<BrowserContext, number>()

/** Serves the fake Turnstile script to every page of `context`, and counts the requests for it. */
export async function fakeTurnstile(context: BrowserContext): Promise<void> {
  turnstileRequests.set(context, 0)
  await context.route(TURNSTILE_SCRIPT, (route) => {
    turnstileRequests.set(context, (turnstileRequests.get(context) ?? 0) + 1)
    return route.fulfill({ contentType: 'text/javascript', body: FAKE_TURNSTILE })
  })
}

/** How many times a page of this context asked for Cloudflare's script. */
export const turnstileScriptRequests = (context: BrowserContext) =>
  turnstileRequests.get(context) ?? 0

/**
 * Sets how the fake widget answers the next starts in this page: `fail` stands in for the
 * always-fail test key (a widget error), `hold` never answers, and `standIn` draws a visible box in
 * the slot. The flags live in the page, so set them after `goto` (or again after a reload).
 */
export async function setTurnstile(
  page: Page,
  flags: { fail?: boolean; hold?: boolean; standIn?: boolean },
): Promise<void> {
  await page.evaluate((f) => {
    const w = window as unknown as Record<string, boolean>
    w.__turnstileFail = !!f.fail
    w.__turnstileHold = !!f.hold
    w.__turnstileStandIn = !!f.standIn
  }, flags)
}

/**
 * A browser context a test makes for itself (a second person, another timezone). Never call
 * `browser.newContext()` in a spec: a context made that way escapes the per-test guard. This one is
 * watched from the start, and its `close()` fails if the page reported a CSP violation, so close it
 * as the test would any context (a unit test, `e2e-contexts.test.ts`, enforces the rule).
 */
export async function guardedContext(
  browser: Browser,
  options?: BrowserContextOptions,
): Promise<BrowserContext> {
  const context = await browser.newContext(options)
  await fakeTurnstile(context)
  const violations = await watchCsp(context)
  const close = context.close.bind(context)
  context.close = async (...args: Parameters<BrowserContext['close']>) => {
    // Let a violation queued by the last action reach the binding before it is read.
    await new Promise((resolve) => setTimeout(resolve, 50))
    const seen = violations()
    await close(...args)
    expect(seen, 'Content Security Policy violations').toEqual([])
  }
  return context
}

export const test = base.extend<{ cspGuard: void }>({
  cspGuard: [
    async ({ context }, use) => {
      await fakeTurnstile(context)
      const violations = await watchCsp(context)
      await use()
      // Let a violation queued by the last action reach the binding before it is read.
      await new Promise((resolve) => setTimeout(resolve, 50))
      expect(violations(), 'Content Security Policy violations').toEqual([])
    },
    { auto: true },
  ],
})

export { expect }
