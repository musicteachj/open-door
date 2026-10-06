import { defineConfig } from 'orval'

// Orval owns src/api/: `clean` deletes any other file there. Hand-written API code goes elsewhere.
export default defineConfig({
  openDoor: {
    input: './openapi.json',
    output: {
      target: './src/api/generated.ts',
      client: 'react-query',
      httpClient: 'fetch',
      mode: 'single',
      clean: true,
      override: {
        // Every call goes through apiFetch: CSRF header, JSON content type, and ApiError on failure.
        mutator: { path: './src/lib/api-fetch.ts', name: 'apiFetch' },
        fetch: { includeHttpResponseReturnType: false },
      },
    },
  },
})
