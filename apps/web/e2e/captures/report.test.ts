import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { GALLERY_STATE_IDS } from '../gallery-ids'
import { AREAS, buildFile, COMPONENT_ROWS, designFile, SCREEN_ROWS, specimenPath } from './manifest'
import { renderReport, type ReportRow } from './report'

const row = (over: Partial<ReportRow> = {}): ReportRow => ({
  title: 'Nav item, current',
  design: 'design/navigation.png',
  build: 'build/nav-item-current.png',
  ...over,
})

const rowsOf = (html: string) => html.match(/<section class="row"/g) ?? []

describe('renderReport', () => {
  it('puts the design on the left and the build on the right', () => {
    const html = renderReport([row()])
    const design = html.indexOf('src="design/navigation.png"')
    const build = html.indexOf('src="build/nav-item-current.png"')
    expect(design).toBeGreaterThan(-1)
    expect(build).toBeGreaterThan(design)
    expect(html.indexOf('>Design<')).toBeLessThan(html.indexOf('>Build<'))
  })

  it('shows a visible note, and no image, for a missing picture', () => {
    const html = renderReport([row({ design: null })])
    expect(html).toContain('Not captured')
    expect(html).not.toContain('design/navigation.png')
    expect(html).toContain('src="build/nav-item-current.png"')
  })

  it('shows the note on both sides when neither was captured', () => {
    const html = renderReport([row({ design: null, build: null })])
    expect(html.match(/Not captured/g)).toHaveLength(2)
    expect(html).not.toContain('<img')
  })

  it('escapes the title, the note, the alt text, and the paths', () => {
    const evil = '<script>alert(1)</script> & "quoted"'
    const html = renderReport([
      row({ title: evil, note: `<b>${evil}</b>`, design: 'a"onerror="x.png' }),
    ])
    expect(html).not.toContain('<script')
    expect(html).not.toContain('<b>')
    expect(html).not.toContain('"onerror="')
    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;quoted&quot;')
    expect(html).toMatch(/alt="Design: &lt;script&gt;/)
  })

  it('has one row per state', () => {
    const html = renderReport([row(), row({ title: 'Other' }), row({ title: 'Third' })])
    expect(rowsOf(html)).toHaveLength(3)
  })

  it('is self-contained: no external styles, scripts, or links', () => {
    const html = renderReport([row()])
    expect(html).toMatch(/^<!doctype html>/i)
    expect(html).toContain('<style>')
    expect(html).not.toMatch(/<link|<script|https?:\/\//)
  })

  it('says so when there are no rows', () => {
    const html = renderReport([])
    expect(rowsOf(html)).toHaveLength(0)
    expect(html).toContain('Nothing to compare yet')
  })

  it('prints a heading when the group changes', () => {
    const html = renderReport([
      row({ group: 'navigation' }),
      row({ title: 'b', group: 'navigation' }),
      row({ title: 'c', group: 'forms' }),
    ])
    expect(html.match(/class="group"/g)).toHaveLength(2)
  })
})

describe('the manifest', () => {
  const ids = new Set<string>(GALLERY_STATE_IDS)

  it('names only real gallery states', () => {
    for (const r of COMPONENT_ROWS) expect(ids.has(r.id), r.id).toBe(true)
  })

  it('gives every row its own picture', () => {
    const files = COMPONENT_ROWS.map(buildFile)
    expect(new Set(files).size).toBe(files.length)
  })

  it('names the picture files the spec writes, relative to the report', () => {
    // The spec takes every path it hands the report from these two functions.
    for (const file of [...AREAS.map(designFile), ...COMPONENT_ROWS.map(buildFile)]) {
      expect(file).toMatch(/^(design|build)\/[a-z0-9-]+\.png$/)
    }
  })

  it('names the overlay each overlay row must show', () => {
    for (const r of COMPONENT_ROWS.filter((x) => x.overlay)) expect(r.interaction, r.id).toBeDefined()
  })

  it('photographs a nav item with keyboard focus, as the specimen draws it', () => {
    expect(
      COMPONENT_ROWS.some((r) => r.id.startsWith('nav-item') && r.interaction?.action === 'focus'),
    ).toBe(true)
  })

  it('points every row at a specimen page that exists', () => {
    for (const r of COMPONENT_ROWS) {
      expect(AREAS).toContain(r.area)
      expect(existsSync(resolve(import.meta.dirname, '../../../..', specimenPath(r.area)))).toBe(true)
    }
  })

  it('has no screen rows yet', () => {
    expect(SCREEN_ROWS).toEqual([])
  })
})
