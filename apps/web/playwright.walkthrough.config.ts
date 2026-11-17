import { defineConfig, devices } from '@playwright/test'

// `make walkthrough` (Phase 8, Task 45): records the guided tour for the walkthrough page. Not a
// test, and never in CI or `make check`: playwright.config.ts ignores e2e/walkthrough/. The
// launcher (scripts/walkthrough/record.py) starts the production image on its own database first
// and passes its origin; with the real model every question here is a paid call.
const BASE_URL = process.env.WALKTHROUGH_BASE_URL ?? 'http://localhost:8300'

export default defineConfig({
  testDir: './e2e/walkthrough',
  testMatch: 'record.ts',
  workers: 1,
  retries: 0,
  reporter: 'line',
  // One take: about three minutes on screen, plus the model's waits.
  timeout: 900_000,
  outputDir: process.env.WALKTHROUGH_OUT ? `${process.env.WALKTHROUGH_OUT}/playwright` : undefined,
  use: {
    ...devices['Desktop Chrome'],
    baseURL: BASE_URL,
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    // The real model's answers can take a while to stream.
    actionTimeout: 30_000,
  },
})
