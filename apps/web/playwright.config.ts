import { defineConfig, devices } from '@playwright/test'

// The browser tests run against the built web app, served by `vite preview` on :4173, and a real
// API on :8100 with the real database. Neither collides with `make dev` (:5173 and :8000).
// Locally both servers are reused if already running; in CI they always start fresh.
const WEB_ORIGIN = 'http://localhost:4173'
const API_ORIGIN = 'http://127.0.0.1:8100'

export default defineConfig({
  testDir: './e2e',
  // Every spec starts its own sandbox, so files run side by side.
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
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
      env: { APP_ORIGIN: WEB_ORIGIN },
      reuseExistingServer: !process.env.CI,
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
