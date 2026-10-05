import { afterEach, describe, expect, it, vi } from 'vitest'

// The gallery's route is built from import.meta.env when router.tsx loads, so each case sets the
// flags first and loads a fresh copy of the module.
async function loadRoutes() {
  vi.resetModules()
  return (await import('./router')).routes
}

const hasGallery = (routes: Awaited<ReturnType<typeof loadRoutes>>) =>
  routes[0].children?.some((route) => route.path === '/gallery') ?? false

describe('the gallery route', () => {
  afterEach(() => {
    vi.resetModules()
  })

  it('exists in development', async () => {
    vi.stubEnv('DEV', true)
    vi.stubEnv('VITE_GALLERY', '')
    expect(hasGallery(await loadRoutes())).toBe(true)
  })

  it('exists when VITE_GALLERY is true, as in the e2e build', async () => {
    vi.stubEnv('DEV', false)
    vi.stubEnv('VITE_GALLERY', 'true')
    expect(hasGallery(await loadRoutes())).toBe(true)
  })

  it('does not exist in a production build', async () => {
    vi.stubEnv('DEV', false)
    vi.stubEnv('VITE_GALLERY', '')
    expect(hasGallery(await loadRoutes())).toBe(false)
  })
})
