import { existsSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { GALLERY_STATE_IDS } from '../gallery-ids'
import {
  conversationRow,
  designScreenFile,
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

  it('set each screenshot beside the real /ask page in the state of the same name', () => {
    for (const row of rows) {
      const file = row.designImage.split('/').pop()!.replace(/^desktop-/, '').replace(/\.png$/, '')
      expect(row.scenario, row.title).toBe(file)
      expect(row.setup).toBe('conversation')
      expect(row.route).toBe('/ask')
      expect(row.persona, row.title).toBeDefined()
      // The design is drawn at 1440 by 900, so the page is photographed at that size, whole.
      expect(row.target).toBe('viewport')
      expect(row.viewport).toBeUndefined()
    }
  })

  it('cover every conversation state the design has, once, in the gallery\'s order', () => {
    expect(rows.map((row) => `conversation-${row.scenario}`)).toEqual(conversationIds)
  })

  it('name a scenario for every conversation row, and no other row uses one', () => {
    for (const row of SCREEN_ROWS) {
      expect(row.scenario !== undefined, row.title).toBe(row.setup === 'conversation')
    }
  })

  it('show the page, never the gallery, and say which states are stubbed', () => {
    for (const row of rows) {
      expect(row.route, row.title).not.toContain('gallery')
    }
    // The states the scripted model can't reach are labeled as stubs in the report.
    const stubbed = rows.filter((row) => row.note?.startsWith('STUB'))
    expect(stubbed.map((row) => row.scenario).sort()).toEqual(
      [
        'budget-daily',
        'budget-sandbox',
        'long-conversation',
        'send-error',
        'stopped',
        'streaming-progress-note',
        'streaming-searching',
        'streaming-text',
      ].sort(),
    )
  })

  it('also set the 06 docked passage panel beside the real page, with the panel open', () => {
    const docked = SCREEN_ROWS.find((row) => row.designImage.endsWith('06-handbook/desktop-panel-docked.png'))
    expect(docked?.setup).toBe('conversation')
    expect(docked?.scenario).toBe('source-panel')
    expect(docked?.differsUntil).toBeUndefined()
  })

  it('leave the home composer states without a "differs until": the failed send is on the conversation page now', () => {
    const composer = SCREEN_ROWS.find((row) => row.setup === 'composer-states')
    expect(composer?.differsUntil).toBeUndefined()
  })
})

describe('conversationRow', () => {
  it('names a real-page scenario for every suffix it accepts', () => {
    const row = conversationRow('cited-answer', 'Cited answer')
    expect(row.scenario).toBe('cited-answer')
    expect(row.setup).toBe('conversation')
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
