import { describe, expect, it } from 'vitest'
import main from './main.tsx?raw'

describe('main.tsx', () => {
  it('installs the announcer before the first render, so its live regions are in the page first', () => {
    const install = main.indexOf('installAnnouncer()')
    const render = main.indexOf('createRoot(')
    expect(main).toContain("import { installAnnouncer } from './lib/announce'")
    expect(install).toBeGreaterThan(-1)
    expect(render).toBeGreaterThan(-1)
    expect(install).toBeLessThan(render)
  })
})
