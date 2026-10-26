import { defineConfig, devices } from '@playwright/test'

// `make captures`: photographs the gallery build and the design specimens, then writes
// captures/index.html. A local development tool. CI never runs it: playwright.config.ts ignores
// e2e/captures/, and no workflow or `make check` target calls this config.
//
// It needs a network, because the specimen pages load React and Babel from unpkg.com. It also
// needs Postgres up with the login users (`make db`), because the screens start real sandboxes.
//
// Three servers. The web and specimen servers are reused if already running. The API is not: it
// must be the one this config starts, with the scripted model, so a stray server on :8100 fails the
// run on the busy port.
//  - The API on :8100, the same one `make e2e` starts (see playwright.config.ts).
//  - `vite preview` on :4173 serves dist-e2e/, which `make captures` builds first with the gallery
//    (the same build `make e2e` uses), and forwards /api to the API.
//  - Python's built-in http.server on :8101 serves docs/design/system. The specimens fetch() their
//    component sketches, which file:// forbids. Python is already a project prerequisite (uv), so
//    there is nothing new to install.
export const WEB_ORIGIN = 'http://localhost:4173'
export const SPECIMEN_ORIGIN = 'http://127.0.0.1:8101'
const API_ORIGIN = 'http://127.0.0.1:8100'

export default defineConfig({
  testDir: './e2e/captures',
  // As in playwright.config.ts: the run's daily AI ledger rows are deleted when it ends.
  globalSetup: './e2e/ledger-cleanup.ts',
  testMatch: 'capture.spec.ts',
  workers: 1,
  retries: 0,
  reporter: 'list',
  // The whole run is one test: the gallery states and every screen, about 100 rows. Phase 5's
  // screens 08 to 10 added 53 that start real sandboxes and sign in as two people.
  timeout: 900_000,
  use: {
    baseURL: WEB_ORIGIN,
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: [
    {
      // As in playwright.config.ts: `env -u` because an agent shell may export ANTHROPIC_API_KEY
      // as an empty string, which would shadow the key in .env.
      command: 'env -u ANTHROPIC_API_KEY uv run uvicorn --factory app.main:create_app --port 8100',
      cwd: '../api',
      url: `${API_ORIGIN}/api/v1/health`,
      // AI_TRANSPORT is pinned on the API this config starts, and `reuseExistingServer` is false so
      // no other API can stand in for it: a local .env set to `anthropic`, or a stray server on
      // :8100, can't make the captures pay for calls (a busy :8100 fails the run instead).
      // The daily budget is raised because a stopped or failed turn keeps its
      // reservation (ADR 0011, "errs toward spending less"), about $0.17 each, so the scripted
      // Stop and error tests would otherwise use up the demo's $3 day and every later turn would
      // get the daily banner. The ledger is shared by every run on the same database.
      env: { APP_ORIGIN: WEB_ORIGIN, AI_TRANSPORT: 'scripted', AI_DAILY_BUDGET_USD: '1000' },
      reuseExistingServer: false,
      stdout: 'ignore',
      stderr: 'ignore',
    },
    {
      command: 'npm run preview -- --outDir dist-e2e',
      url: WEB_ORIGIN,
      env: { API_PROXY_TARGET: API_ORIGIN },
      reuseExistingServer: true,
      stdout: 'ignore',
      stderr: 'ignore',
    },
    {
      command: 'python3 -m http.server 8101 --bind 127.0.0.1 --directory ../../docs/design/system',
      url: SPECIMEN_ORIGIN,
      reuseExistingServer: true,
      stdout: 'ignore',
      stderr: 'ignore',
    },
  ],
})
