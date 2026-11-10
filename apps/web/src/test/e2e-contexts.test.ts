import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, it } from 'vitest'

// A browser context a browser test makes with `browser.newContext()`, or `browser.newPage()` (which
// makes one too), escapes the Content Security Policy guard (e2e/fixtures.ts). Specs and helpers use `guardedContext` instead. Only the guard's
// own file, and the proof spec that tests the guard, may call it.
const e2eDir = join(import.meta.dirname, '../../e2e')
const ALLOWED = new Set(['fixtures.ts', 'csp-guard.spec.ts'])

it('no browser test makes a bare context', () => {
  // Recursive: Playwright finds specs in subfolders too. `captures/` is `make captures`'s own
  // config (playwright.captures.config.ts), which the browser suite ignores and CI never runs.
  const offenders = readdirSync(e2eDir, { recursive: true, encoding: 'utf8' })
    .filter((name) => name.endsWith('.ts') && !ALLOWED.has(name))
    .filter((name) => !name.startsWith('captures/'))
    .filter((name) =>
      /\.newContext\(|\bbrowser\.newPage\(/.test(readFileSync(join(e2eDir, name), 'utf8')),
    )
  expect(offenders, 'use guardedContext from ./fixtures').toEqual([])
})
