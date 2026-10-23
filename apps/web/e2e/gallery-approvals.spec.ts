import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Locator, type Page } from '@playwright/test'
import { GALLERY_STATE_IDS } from './gallery-ids'
import {
  AXE_TAGS,
  MODAL_OVERLAY_RULES,
  expectSectionHeadings,
  galleryState as state,
  galleryStateSelector,
  openGallery,
  statesPastEdge,
  themeColor,
} from './helpers'

// The approvals section of the gallery in a real browser: axe on every state, the decision
// dialogs' real box and focus, Approve and Deny looking the same, the coverage ink, and 390 px.

const APPROVALS_IDS = GALLERY_STATE_IDS.slice(
  GALLERY_STATE_IDS.indexOf('approval-card-default'),
  GALLERY_STATE_IDS.indexOf('decision-dialog-deciding') + 1,
)
// These start closed, behind a button.
const HOSTS: Record<string, string> = {
  'decision-dialog-approve': 'Open the approve dialog',
  'decision-dialog-deny': 'Open the deny dialog',
  'decision-dialog-deciding': 'Open the deciding dialog',
}

test.beforeEach(async ({ page }) => {
  await openGallery(page)
})

test('every approvals state has its own heading', async ({ page }) => {
  await expectSectionHeadings(page, APPROVALS_IDS)
  for (const id of APPROVALS_IDS) await expect(page.locator(`h3#${id}`)).toHaveCount(1)
})

for (const id of APPROVALS_IDS) {
  test(`${id} has no accessibility violations`, async ({ page }) => {
    const open = HOSTS[id]
    if (open) {
      await state(page, id).getByRole('button', { name: open }).click()
      await expect(page.getByRole('alertdialog')).toBeVisible()
      const results = await new AxeBuilder({ page })
        .withTags(AXE_TAGS)
        .disableRules(MODAL_OVERLAY_RULES)
        .analyze()
      expect(results.violations).toEqual([])
      return
    }
    const results = await new AxeBuilder({ page })
      .withTags(AXE_TAGS)
      .include(galleryStateSelector(id))
      .analyze()
    expect(results.violations).toEqual([])
  })
}

const style = (target: Locator) =>
  target.evaluate((el) => {
    const css = getComputedStyle(el)
    const box = el.getBoundingClientRect()
    return {
      background: css.backgroundColor,
      border: `${css.borderTopWidth} ${css.borderTopStyle} ${css.borderTopColor}`,
      color: css.color,
      fontSize: css.fontSize,
      fontWeight: css.fontWeight,
      height: box.height,
    }
  })

test.describe('Approve and Deny', () => {
  const buttons = (page: Page) => {
    const card = state(page, 'approval-card-default')
    return {
      approve: card.getByRole('button', { name: /^Approve Zara Bautista’s PTO/ }),
      deny: card.getByRole('button', { name: /^Deny Zara Bautista’s PTO/ }),
    }
  }

  test('are named for the request', async ({ page }) => {
    const { approve, deny } = buttons(page)
    await expect(approve).toHaveAccessibleName('Approve Zara Bautista’s PTO, November 9 to 10')
    await expect(deny).toHaveAccessibleName('Deny Zara Bautista’s PTO, November 9 to 10')
    await expect(approve).toHaveText('Approve')
    await expect(deny).toHaveText('Deny')
  })

  test('look the same at rest', async ({ page }) => {
    const { approve, deny } = buttons(page)
    await approve.scrollIntoViewIfNeeded()
    expect(await style(approve)).toEqual(await style(deny))
  })

  test('look the same on hover', async ({ page }) => {
    const { approve, deny } = buttons(page)
    await approve.scrollIntoViewIfNeeded()
    await approve.hover()
    const hoverFill = await themeColor(page, 'surface-hover')
    await expect.poll(async () => (await style(approve)).background).toBe(hoverFill)
    const approved = await style(approve)
    await deny.hover()
    await expect.poll(async () => (await style(deny)).background).toBe(hoverFill)
    expect(await style(deny)).toEqual(approved)
    // And neither is a primary button.
    expect(approved.background).not.toBe(await themeColor(page, 'primary'))
  })
})

test('the coverage lines are in the body ink, with no color of their own', async ({ page }) => {
  const ink = await themeColor(page, 'ink')
  for (const id of [
    'coverage-line-one-person',
    'coverage-line-none',
    'coverage-line-part-of-day',
  ]) {
    const lines = state(page, id).locator('[data-slot="coverage-line"] span.text-ui')
    expect(await lines.count(), id).toBeGreaterThan(0)
    for (const line of await lines.all()) {
      expect(await line.evaluate((el) => getComputedStyle(el).color), id).toBe(ink)
    }
    // No warning or alert in the line: it is context, not a verdict.
    await expect(state(page, id).locator('[role="alert"], [role="status"]')).toHaveCount(0)
  }
})

test.describe('the decision dialogs', () => {
  const dialog = (page: Page) => page.getByRole('alertdialog')
  const opener = (page: Page, id: string) =>
    state(page, id).getByRole('button', { name: HOSTS[id]! })

  test.describe('at 1440 px', () => {
    test.use({ viewport: { width: 1440, height: 900 } })

    test('the box is 480 px wide and centered, over a scrim that covers the window', async ({
      page,
    }) => {
      await opener(page, 'decision-dialog-approve').click()
      const box = (await dialog(page).boundingBox())!
      expect(box.width).toBe(480)
      expect(Math.abs(box.x + box.width / 2 - 720)).toBeLessThanOrEqual(1)
      expect(Math.abs(box.y + box.height / 2 - 450)).toBeLessThanOrEqual(1)
      const scrim = (await page.locator('[data-slot="alert-dialog-overlay"]').boundingBox())!
      expect(scrim).toEqual({ x: 0, y: 0, width: 1440, height: 900 })
    })
  })

  test('the approve dialog starts focus on "Go back"', async ({ page }) => {
    await opener(page, 'decision-dialog-approve').click()
    await expect(dialog(page).getByRole('button', { name: 'Go back' })).toBeFocused()
  })

  test('the deny dialog starts focus in the note', async ({ page }) => {
    await opener(page, 'decision-dialog-deny').click()
    await expect(dialog(page).getByRole('textbox')).toBeFocused()
  })

  for (const id of ['decision-dialog-approve', 'decision-dialog-deny']) {
    test(`${id}: Tab and Shift+Tab stay inside`, async ({ page }) => {
      await opener(page, id).click()
      for (const key of ['Tab', 'Tab', 'Tab', 'Tab', 'Shift+Tab', 'Shift+Tab', 'Shift+Tab']) {
        await page.keyboard.press(key)
        expect(
          await page.evaluate(
            () => document.activeElement?.closest('[role="alertdialog"]') != null,
          ),
        ).toBe(true)
      }
    })

    test(`${id}: Escape goes back and returns focus to the button that opened it`, async ({
      page,
    }) => {
      await opener(page, id).click()
      await expect(dialog(page)).toBeVisible()
      await page.keyboard.press('Escape')
      await expect(dialog(page)).toBeHidden()
      await expect(opener(page, id)).toBeFocused()
    })
  }

  test('"Go back" returns focus to the button that opened it', async ({ page }) => {
    await opener(page, 'decision-dialog-deny').click()
    await dialog(page).getByRole('button', { name: 'Go back' }).click()
    await expect(dialog(page)).toBeHidden()
    await expect(opener(page, 'decision-dialog-deny')).toBeFocused()
  })

  test('while deciding, Escape does nothing, Go back is disabled, and the button is busy', async ({
    page,
  }) => {
    await opener(page, 'decision-dialog-deciding').click()
    const confirm = dialog(page).getByRole('button', { name: 'Approving…' })
    await expect(confirm).toBeVisible()
    await expect(confirm).toHaveAttribute('aria-disabled', 'true')
    await expect(confirm).toHaveAttribute('aria-busy', 'true')
    await expect(dialog(page).getByRole('button', { name: 'Go back' })).toBeDisabled()
    await page.keyboard.press('Escape')
    await expect(dialog(page)).toBeVisible()
  })

  test.describe('at 390 px', () => {
    test.use({ viewport: { width: 390, height: 844 } })

    for (const [id, confirmName] of [
      ['decision-dialog-approve', 'Approve'],
      ['decision-dialog-deny', 'Deny'],
    ] as const) {
      test(`${id}: the box keeps 16 px from each side, with the buttons stacked and the confirm on top`, async ({
        page,
      }) => {
        await opener(page, id).click()
        const box = (await dialog(page).boundingBox())!
        expect(box.x).toBe(16)
        expect(box.width).toBe(390 - 32)
        const confirm = (await dialog(page)
          .getByRole('button', { name: confirmName, exact: true })
          .boundingBox())!
        const back = (await dialog(page).getByRole('button', { name: 'Go back' }).boundingBox())!
        expect(confirm.y + confirm.height).toBeLessThanOrEqual(back.y)
        for (const button of [confirm, back]) {
          expect(button.x).toBeCloseTo(box.x + 24, 0)
          expect(button.width).toBeCloseTo(box.width - 48, 0)
        }
        const scrim = (await page.locator('[data-slot="alert-dialog-overlay"]').boundingBox())!
        expect(scrim).toEqual({ x: 0, y: 0, width: 390, height: 844 })
      })
    }
  })
})

test.describe('at 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('nothing in the approvals section scrolls sideways', async ({ page }) => {
    await expect(page.locator('h3#approval-card-default')).toBeAttached()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    expect(await statesPastEdge(page, APPROVALS_IDS, 390)).toEqual([])
  })

  test('Approve and Deny are half the card each, side by side, below the details', async ({
    page,
  }) => {
    const card = state(page, 'approval-card-default').locator('[data-slot="approval-card"]')
    const approve = (await card.getByRole('button', { name: /^Approve/ }).boundingBox())!
    const deny = (await card.getByRole('button', { name: /^Deny/ }).boundingBox())!
    const dates = (await card
      .getByText('Monday, November 9 to Tuesday, November 10')
      .boundingBox())!
    expect(Math.abs(approve.width - deny.width)).toBeLessThanOrEqual(1)
    expect(approve.x).toBeLessThan(deny.x)
    expect(Math.abs(approve.y - deny.y)).toBeLessThanOrEqual(1)
    expect(approve.y).toBeGreaterThan(dates.y + dates.height)
    // The two share the card's width inside its 16 px padding, less the gap.
    const box = (await card.boundingBox())!
    expect(approve.width + deny.width + 12).toBeCloseTo(box.width - 2 - 32, 0)
  })

  test('a decided team request row stacks: the person, then the dates, then the badge', async ({
    page,
  }) => {
    const row = state(page, 'request-row-team').locator('[data-slot="request-row"]')
    const [person, dates, badge] = await Promise.all(
      [0, 1, 2].map((i) => row.locator(':scope > div').nth(i).boundingBox()),
    )
    expect(person!.y + person!.height).toBeLessThanOrEqual(dates!.y + 1)
    expect(dates!.y + dates!.height).toBeLessThanOrEqual(badge!.y + 1)
    await expect(row.getByText(/^Approved Oct/)).toBeVisible()
    // The avatar and name share a line.
    const avatar = (await row.locator('[data-slot="avatar"]').boundingBox())!
    const name = (await row.getByText('Vikram Morales').boundingBox())!
    expect(Math.abs(avatar.y + avatar.height / 2 - (name.y + name.height / 2))).toBeLessThanOrEqual(
      12,
    )
  })
})
