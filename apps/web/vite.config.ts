import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { configDefaults, defineConfig } from 'vitest/config'

// The dev server forwards /api to the FastAPI server, so the browser talks to one origin
// in development exactly as it will in production. `vite preview` forwards it too, to the same
// target unless API_PROXY_TARGET says otherwise: the e2e run points it at its own API on :8100.
const proxy = { '/api': process.env.API_PROXY_TARGET ?? 'http://localhost:8000' }

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy,
  },
  preview: { port: 4173, strictPort: true, proxy },
  test: {
    environment: 'jsdom',
    // The browser tests in e2e/ belong to Playwright, and so does the capture run. The one file
    // there that Vitest runs is the capture report's test, which the default include already
    // finds because the report is a pure function: it is the only e2e file not named *.spec.ts.
    exclude: [...configDefaults.exclude, 'e2e/**/*.spec.ts', 'dist-e2e/**'],
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
    unstubGlobals: true,
  },
})
