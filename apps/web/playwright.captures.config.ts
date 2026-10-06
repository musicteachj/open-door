import { defineConfig, devices } from '@playwright/test'

// `make captures`: photographs the gallery build and the design specimens, then writes
// captures/index.html. A local development tool. CI never runs it: playwright.config.ts ignores
// e2e/captures/, and no workflow or `make check` target calls this config.
//
// It needs a network, because the specimen pages load React and Babel from unpkg.com.
//
// Two servers, both reused if already running:
//  - `vite preview` on :4173 serves dist-e2e/, which `make captures` builds first with the gallery
//    (the same build `make e2e` uses). The gallery needs no API.
//  - Python's built-in http.server on :8101 serves docs/design/system. The specimens fetch() their
//    component sketches, which file:// forbids. Python is already a project prerequisite (uv), so
//    there is nothing new to install.
export const WEB_ORIGIN = 'http://localhost:4173'
export const SPECIMEN_ORIGIN = 'http://127.0.0.1:8101'

export default defineConfig({
  testDir: './e2e/captures',
  testMatch: 'capture.spec.ts',
  workers: 1,
  retries: 0,
  reporter: 'list',
  timeout: 300_000,
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
      command: 'npm run preview -- --outDir dist-e2e',
      url: WEB_ORIGIN,
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
