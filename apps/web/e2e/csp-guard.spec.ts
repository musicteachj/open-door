import { expect, test, watchCsp } from './fixtures'

// The proof that the CSP guard in fixtures.ts can see a violation. Only the production image sends a
// CSP (E2E_TARGET=image), so this runs only there. It watches a context of its own (the guarded
// test fixture would fail this very test), loads the app, injects a <style> with no nonce, which
// the page's policy blocks, and expects the guard to have reported a style-src violation. It
// passes only when the page loaded and the violation was reported, so an image that is down or a
// guard that stopped working both fail it.
test.skip(
  process.env.E2E_TARGET !== 'image',
  'The Vite preview sends no CSP, so there is nothing for the guard to catch.',
)

test('the guard reports a style injected without the page nonce', async ({ browser }) => {
  const context = await browser.newContext() // The one place a bare context is right.
  try {
    const violations = await watchCsp(context)
    const page = await context.newPage()
    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    expect(violations(), 'a clean load reports nothing').toEqual([])
    await page.evaluate(() => {
      const style = document.createElement('style')
      style.textContent = 'body { outline: 1px solid red; }'
      document.head.append(style)
    })
    await expect.poll(() => violations().some((line) => line.includes('style-src'))).toBe(true)
  } finally {
    await context.close()
  }
})
