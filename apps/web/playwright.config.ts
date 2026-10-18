import { defineConfig, devices } from '@playwright/test'

// The browser tests run against the built web app, served by `vite preview` on :4173, and a real
// API on :8100 with the real database. Neither collides with `make dev` (:5173 and :8000).
// The API is never reused: a server already on :8100 (started some other way, perhaps with the real
// model) would serve the tests, so the run fails on the busy port instead. The web server is reused
// locally if it is already running (it makes no AI calls); in CI both start fresh.
const WEB_ORIGIN = 'http://localhost:4173'
const API_ORIGIN = 'http://127.0.0.1:8100'

export default defineConfig({
  testDir: './e2e',
  // Notes the database's time before the run and deletes the daily AI ledger rows made since, after.
  globalSetup: './e2e/ledger-cleanup.ts',
  // `make captures` has its own config (playwright.captures.config.ts), and CI never runs it.
  testIgnore: '**/captures/**',
  // Every spec starts its own sandbox, so files run side by side.
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  // CI runs one worker, which is also what the timing-sensitive conversation specs are written for.
  // Locally Playwright picks its own number.
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: WEB_ORIGIN,
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      // `env -u` because an agent shell may export ANTHROPIC_API_KEY as an empty string, which
      // would shadow the key in .env. The API connects with the DATABASE_URLs in apps/api/.env
      // (or the job's environment in CI) and accepts requests from the preview server's origin.
      command: 'env -u ANTHROPIC_API_KEY uv run uvicorn --factory app.main:create_app --port 8100',
      cwd: '../api',
      url: `${API_ORIGIN}/api/v1/health`,
      // AI_TRANSPORT is pinned on the API this config starts, and `reuseExistingServer` is false so
      // no other API can stand in for it: a local .env set to `anthropic`, or a stray server on
      // :8100, can't make the browser tests pay for calls (a busy :8100 fails the run instead).
      // The daily budget is raised because a stopped or failed turn keeps its
      // reservation (ADR 0011, "errs toward spending less"), about $0.17 each, so the scripted
      // Stop and error tests would otherwise use up the demo's $3 day and every later turn would
      // get the daily banner. The ledger is shared by every run on the same database, so
      // e2e/ledger-cleanup.ts deletes the rows a run made when it ends (the API's own tests would
      // fail past the real $3 cap otherwise).
      env: { APP_ORIGIN: WEB_ORIGIN, AI_TRANSPORT: 'scripted', AI_DAILY_BUDGET_USD: '1000' },
      reuseExistingServer: false,
      stdout: 'ignore',
      stderr: 'ignore',
    },
    {
      // Builds with the gallery into dist-e2e/, so the production dist/ is never replaced, then
      // serves it with /api forwarded to the e2e API (vite.config.ts reads API_PROXY_TARGET).
      command: 'npm run build:e2e && npm run preview -- --outDir dist-e2e',
      url: WEB_ORIGIN,
      env: { API_PROXY_TARGET: API_ORIGIN },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      stdout: 'ignore',
      stderr: 'ignore',
    },
  ],
})
