import { existsSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { GALLERY_STATE_IDS } from '../gallery-ids'
import {
  conversationRow,
  designScreenFile,
  galleryFrameSelector,
  SCREEN_FOLDERS,
  SCREEN_ROWS,
  screenSlug,
} from './manifest'

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

  it('give every screenshot in the screen folders exactly one row', () => {
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

describe('the screen 07 rows', () => {
  const rows = SCREEN_ROWS.filter((row) => row.designImage.includes('/07-conversation/'))
  const conversationIds = GALLERY_STATE_IDS.filter((id) => id.startsWith('conversation-'))

  it('set each screenshot beside the gallery state of the same name', () => {
    for (const row of rows) {
      const file = row.designImage.split('/').pop()!.replace(/^desktop-/, '').replace(/\.png$/, '')
      expect(row.galleryId, row.title).toBe(`conversation-${file}`)
      expect(row.setup).toBe('gallery-state')
      expect(row.target).toBe('section')
    }
  })

  it('cover every conversation state in the gallery, once', () => {
    expect(rows.map((row) => row.galleryId)).toEqual(conversationIds)
  })

  it('name a gallery state for every gallery-state row, and no other row does', () => {
    for (const row of SCREEN_ROWS) {
      expect(row.galleryId !== undefined, row.title).toBe(row.setup === 'gallery-state')
      if (row.galleryId) expect(GALLERY_STATE_IDS).toContain(row.galleryId)
    }
  })

  it('open the source panel from its marker, and leave the other states as they load', () => {
    const interactive = rows.filter((row) => row.interaction !== undefined)
    expect(interactive.map((row) => row.galleryId)).toEqual(['conversation-source-panel'])
  })
})

describe('galleryFrameSelector', () => {
  it('photographs the conversation state inside the section, not the section', () => {
    expect(galleryFrameSelector('conversation-crisis')).toBe(
      'section[aria-labelledby="conversation-crisis"] [data-slot="conversation-state"]',
    )
  })
})

describe('conversationRow', () => {
  it('names a gallery state that exists for every suffix it accepts', () => {
    expect(conversationRow('cited-answer', 'Cited answer').galleryId).toBe(
      'conversation-cited-answer',
    )
  })

  it('refuses a misspelled suffix when the project is type checked', () => {
    // The cast it replaces would have let this through, and the capture would have photographed
    // nothing. `tsc -b` is the check: an unused directive here is an error.
    const misspelled = () =>
      // @ts-expect-error "cited-answr" is not a conversation state in the gallery
      conversationRow('cited-answr', 'Cited answer')
    expect(misspelled).toBeTypeOf('function')
  })
})
