import { setNonce } from 'get-nonce'

// The API writes a fresh nonce into this meta tag on every page it serves, and the same nonce into
// the Content-Security-Policy header. In development Vite serves the page, the tag is empty, and
// there is no policy to satisfy.
export function readNonce(): string | undefined {
  const content = document.querySelector<HTMLMetaElement>('meta[name="csp-nonce"]')?.content
  return content ? content : undefined
}

// Radix's scroll lock injects a <style> tag through get-nonce, so give it the page's nonce before
// anything renders.
export function applyNonce(): void {
  const nonce = readNonce()
  if (nonce) setNonce(nonce)
}
