import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll } from 'vitest'
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
  // Radix Select scrolls the highlighted option into view.
  Element.prototype.scrollIntoView = () => {}
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
  server.resetHandlers()
})

afterAll(() => {
  server.close()
})
