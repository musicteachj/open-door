import { existsSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { designScreenFile, SCREEN_FOLDERS, SCREEN_ROWS, screenSlug } from './manifest'

const REPO_ROOT = resolve(import.meta.dirname, '../../../..')
const SCREENS = 'docs/design/screens'

describe('the screen rows', () => {
  const pngs = SCREEN_FOLDERS.flatMap((folder) =>
    readdirSync(resolve(REPO_ROOT, SCREENS, folder))
      .filter((name) => name.endsWith('.png'))
      .map((name) => `${SCREENS}/${folder}/${name}`),
  )

  it('find the design folders, and screenshots in each', () => {
    expect(pngs.length).toBeGreaterThanOrEqual(20)
    for (const folder of SCREEN_FOLDERS) {
      expect(pngs.some((png) => png.includes(`/${folder}/`))).toBe(true)
    }
  })

  it('give every screenshot in 01, 02, 03, and 05 exactly one row', () => {
    for (const png of pngs) {
      const rows = SCREEN_ROWS.filter((row) => row.designImage === png)
      expect(rows.length, `${png} needs exactly one row in SCREEN_ROWS`).toBe(1)
    }
  })

  it('point only at screenshots that exist', () => {
    for (const row of SCREEN_ROWS) {
      expect(existsSync(resolve(REPO_ROOT, row.designImage)), row.designImage).toBe(true)
      expect(pngs).toContain(row.designImage)
    }
  })

  it('have their own title and picture name', () => {
    expect(new Set(SCREEN_ROWS.map((row) => row.title)).size).toBe(SCREEN_ROWS.length)
    expect(new Set(SCREEN_ROWS.map(screenSlug)).size).toBe(SCREEN_ROWS.length)
    expect(designScreenFile(SCREEN_ROWS[0]!)).toMatch(/^design\/screens\/.+\.png$/)
  })

  it('say which phase adds what a row cannot show yet', () => {
    for (const row of SCREEN_ROWS.filter((r) => r.differsUntil !== undefined)) {
      expect(row.differsUntil, row.title).toMatch(/^Phase \d/)
    }
  })
})
