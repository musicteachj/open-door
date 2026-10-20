import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { resetAnnouncer } from '@/lib/announce'
import { server } from './msw'

beforeAll(() => {
  // jsdom does not implement scrolling; <ScrollRestoration> calls it on every navigation.
  window.scrollTo = () => {}
  // The next few stand in for browser APIs jsdom leaves out and Radix's primitives call. They do
  // nothing, which is all the tests need: the behavior under test is Radix's own state, not layout.
  // Radix Select and Toast ask whether a pointer is captured.
  Element.prototype.hasPointerCapture = () => false
  Element.prototype.setPointerCapture = () => {}
  Element.prototype.releasePointerCapture = () => {}
  // Radix Select scrolls the highlighted option into view. Current Chromium's scrollIntoView
  // returns a Promise (jsdom's would return nothing), so the stub does too: an effect that returns
  // it by mistake then fails here, as it does in a real browser ("destroy is not a function").
  Element.prototype.scrollIntoView = () => Promise.resolve() as unknown as undefined
  // Radix Popper (select, menu, tooltip) watches its anchor's size.
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  server.listen({ onUnhandledRequest: 'error' })
})

afterEach(() => {
  cleanup()
  // The announcer's regions live on the body, outside what `cleanup` removes.
  resetAnnouncer()
  server.resetHandlers()
})

afterAll(() => {
  server.close()
})
