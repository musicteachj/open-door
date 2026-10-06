// The browser's icons: every file index.html or the web app manifest names must exist in public/,
// so a renamed or missing icon fails here rather than showing the browser's blank page icon.
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const web = join(import.meta.dirname, '..', '..')
const html = readFileSync(join(web, 'index.html'), 'utf8')
const linked = [...html.matchAll(/<link[^>]+href="\/([^"]+)"/g)].map((m) => m[1]!)

describe('brand icons', () => {
  it('links the SVG favicon, the PNG fallbacks, the Apple touch icon, and the manifest', () => {
    expect(html).toMatch(/<link rel="icon" type="image\/svg\+xml" href="\/favicon\.svg"/)
    expect(html).toMatch(
      /<link rel="icon" type="image\/png" sizes="32x32" href="\/favicon-32\.png"/,
    )
    expect(html).toMatch(
      /<link rel="icon" type="image\/png" sizes="16x16" href="\/favicon-16\.png"/,
    )
    expect(html).toMatch(/<link rel="apple-touch-icon" href="\/apple-touch-icon\.png"/)
    expect(html).toMatch(/<link rel="manifest" href="\/site\.webmanifest"/)
  })

  it('finds every linked file in public/', () => {
    expect(linked.length).toBeGreaterThanOrEqual(5)
    expect(linked.filter((file) => !existsSync(join(web, 'public', file)))).toEqual([])
  })

  it('names the app and its 512 px icon in the manifest, and the icon exists', () => {
    const manifest = JSON.parse(readFileSync(join(web, 'public', 'site.webmanifest'), 'utf8')) as {
      name: string
      icons: { src: string; sizes: string }[]
    }
    expect(manifest.name).toBe('Open Door')
    expect(manifest.icons.map((icon) => icon.sizes)).toContain('512x512')
    for (const icon of manifest.icons) {
      expect(existsSync(join(web, 'public', icon.src.replace(/^\//, '')))).toBe(true)
    }
  })
})
