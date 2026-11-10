import {
  expect,
  test as base,
  type Browser,
  type BrowserContext,
  type BrowserContextOptions,
  type ConsoleMessage,
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
