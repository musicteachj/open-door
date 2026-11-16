import { defineConfig, devices } from '@playwright/test'

// The live check through the production image (Phase 8, Task 46). Not a test, and never in CI or
// `make check`: playwright.config.ts ignores e2e/live/. scripts/prod-local/live_check.py starts the
// image on its own database first and passes its origin; with the real model it is a paid run.
export default defineConfig({
  testDir: './e2e/live',
  testMatch: 'check.ts',
  workers: 1,
  retries: 0,
  reporter: 'line',
  timeout: 300_000,
  outputDir: process.env.LIVE_OUT ? `${process.env.LIVE_OUT}/playwright` : undefined,
  use: {
    ...devices['Desktop Chrome'],
    baseURL: process.env.LIVE_BASE_URL ?? 'http://localhost:8300',
    viewport: { width: 1440, height: 900 },
    actionTimeout: 30_000,
  },
})
