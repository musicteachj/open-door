import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router/dom'
import './index.css'
import { createAppRouter } from './app/router'
import { markExpired } from './app/session-status'
import { installAnnouncer } from './lib/announce'
import { applyNonce } from './lib/csp-nonce'
import { createQueryClient } from './lib/query-client'

// The page's nonce goes to get-nonce before anything renders: Radix's scroll lock injects a <style>
// tag through it, and the Content-Security-Policy allows only styles that carry the nonce.
applyNonce()

// The live regions go into the page first, so a screen reader is already watching them when the
// first thing is announced.
installAnnouncer()

const queryClient = createQueryClient({ onUnauthorized: markExpired })
const router = createAppRouter()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
