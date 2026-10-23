import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import { GALLERY_STATE_IDS } from './gallery-ids'
import {
  AXE_TAGS,
  expectSectionHeadings,
  galleryState as state,
  galleryStateSelector,
  openGallery,
  statesPastEdge,
} from './helpers'

// The confirm card section of the gallery in a real browser: axe on every state, what a pending,
// streaming, and deny card say and how Tab moves through them, and 390 px.

const CONFIRM_IDS = GALLERY_STATE_IDS.slice(
  GALLERY_STATE_IDS.indexOf('confirm-card-book-pending'),
  GALLERY_STATE_IDS.indexOf('confirm-card-expired') + 1,
)

test.beforeEach(async ({ page }) => {
  await openGallery(page)
})

test('every confirm card state has its own heading', async ({ page }) => {
  await expectSectionHeadings(page, CONFIRM_IDS)
  for (const id of CONFIRM_IDS) await expect(page.locator(`h3#${id}`)).toHaveCount(1)
})

for (const id of CONFIRM_IDS) {
  test(`${id} has no accessibility violations`, async ({ page }) => {
    // The executed card's line fades in over 200 ms; wait for it to be fully opaque before axe
    // reads its colors.
    await expect
      .poll(() =>
        state(page, id)
          .locator('output')
          .evaluateAll((lines) => lines.every((line) => getComputedStyle(line).opacity === '1')),
      )
      .toBe(true)
    const results = await new AxeBuilder({ page })
      .withTags(AXE_TAGS)
      .include(galleryStateSelector(id))
      .analyze()
    expect(results.violations).toEqual([])
  })
}

test('a pending card says the AI proposed it, and when it expires', async ({ page }) => {
  const card = state(page, 'confirm-card-book-pending')
  await expect(
    card.getByText('Proposed by the AI. Nothing happens until you confirm.'),
  ).toBeVisible()
  await expect(card.getByText('Expires at 3:42 PM')).toBeVisible()
  await expect(card.getByRole('button', { name: /^Confirm: / })).toBeEnabled()
  await expect(card.getByRole('button', { name: /^Dismiss, / })).toBeEnabled()
})

test('a streaming card keeps Confirm aria-disabled and described by the wait, and Dismiss stays live', async ({
  page,
}) => {
  const card = state(page, 'confirm-card-streaming')
  const confirm = card.getByRole('button', { name: /^Confirm: / })
  const dismiss = card.getByRole('button', { name: /^Dismiss, / })
  await expect(confirm).toHaveAttribute('aria-disabled', 'true')
  await expect(confirm).not.toHaveAttribute('disabled', /.*/)
  await expect(confirm).toHaveAccessibleDescription('Wait for the answer to finish')
  // Aria-disabled keeps it focusable, so a keyboard user hears why it waits.
  await confirm.focus()
  await expect(confirm).toBeFocused()
  await expect(dismiss).toBeEnabled()
  await expect(dismiss).not.toHaveAttribute('aria-disabled', 'true')
})

test('the deny card tabs through the note, the source chip, Deny, and Dismiss', async ({
  page,
}) => {
  const card = state(page, 'confirm-card-deny-pending')
  const note = card.getByRole('textbox')
  await note.scrollIntoViewIfNeeded()
  await note.focus()
  const order: string[] = []
  for (let i = 0; i < 3; i += 1) {
    await page.keyboard.press('Tab')
    order.push(
      await page.evaluate(() => {
        const el = document.activeElement!
        return el.getAttribute('data-slot') === 'rule-chip'
          ? 'source chip'
          : (el.textContent ?? '').trim()
      }),
    )
  }
  expect(order).toEqual(['source chip', 'Deny', 'Dismiss'])
})

test('the confirming card shows a busy Confirm and a disabled Dismiss', async ({ page }) => {
  const card = state(page, 'confirm-card-confirming')
  const confirm = card.getByRole('button', { name: 'Confirming…' })
  await expect(confirm).toBeVisible()
  await expect(confirm).toHaveAttribute('aria-busy', 'true')
  await expect(card.getByRole('button', { name: /^Dismiss, / })).toBeDisabled()
})

test.describe('at 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('nothing in the confirm card section scrolls sideways', async ({ page }) => {
    await expect(page.locator('h3#confirm-card-book-pending')).toBeAttached()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    expect(await statesPastEdge(page, CONFIRM_IDS, 390)).toEqual([])
  })

  test('Confirm and Dismiss are each half the footer width', async ({ page }) => {
    const card = state(page, 'confirm-card-book-pending')
    const footer = (await card.locator('[data-slot="confirm-card-footer"]').boundingBox())!
    const confirm = (await card.getByRole('button', { name: /^Confirm: / }).boundingBox())!
    const dismiss = (await card.getByRole('button', { name: /^Dismiss, / }).boundingBox())!
    // The footer has 16 px of padding on each side and a 12 px gap between the buttons.
    const half = (footer.width - 2 - 32 - 12) / 2
    expect(Math.abs(confirm.width - half)).toBeLessThanOrEqual(1)
    expect(Math.abs(dismiss.width - half)).toBeLessThanOrEqual(1)
    expect(confirm.x).toBeLessThan(dismiss.x)
    expect(Math.abs(confirm.y - dismiss.y)).toBeLessThanOrEqual(1)
  })

  test('the facts stack, with each label above its value', async ({ page }) => {
    const card = state(page, 'confirm-card-book-pending')
    const labels = card.locator('dl > dt')
    const values = card.locator('dl > dd')
    const count = await labels.count()
    expect(count).toBeGreaterThanOrEqual(2)
    for (let i = 0; i < count; i += 1) {
      const label = (await labels.nth(i).boundingBox())!
      const value = (await values.nth(i).boundingBox())!
      expect(value.y, `fact ${i}`).toBeGreaterThanOrEqual(label.y + label.height - 1)
      expect(Math.abs(value.x - label.x), `fact ${i}`).toBeLessThanOrEqual(1)
    }
  })

  test('the wait line sits under the buttons on a streaming card', async ({ page }) => {
    const card = state(page, 'confirm-card-streaming')
    const wait = (await card.getByText('Wait for the answer to finish').boundingBox())!
    for (const name of [/^Confirm: /, /^Dismiss, /]) {
      const button = (await card.getByRole('button', { name }).boundingBox())!
      expect(wait.y).toBeGreaterThanOrEqual(button.y + button.height)
    }
  })

  test('the expiry shares the title line while it fits, and drops under the title when it does not', async ({
    page,
  }) => {
    const place = async (id: string, title: string) => {
      const card = state(page, id)
      return {
        title: (await card.getByRole('heading', { name: title, exact: true }).boundingBox())!,
        expiry: (await card.getByText('Expires at 3:42 PM').boundingBox())!,
        card: (await card.locator('[data-slot="confirm-card"]').boundingBox())!,
      }
    }
    // "Book PTO" is short, so the expiry fits beside it.
    const short = await place('confirm-card-book-pending', 'Book PTO')
    expect(Math.abs(short.expiry.y - short.title.y)).toBeLessThanOrEqual(12)
    // "Record sick time" leaves no room, so the expiry drops under it, inside the card.
    const long = await place('confirm-card-sick-pending', 'Record sick time')
    expect(long.expiry.y).toBeGreaterThanOrEqual(long.title.y + long.title.height)
    for (const { expiry, card } of [short, long]) {
      expect(expiry.x + expiry.width).toBeLessThanOrEqual(card.x + card.width)
    }
  })

  test('the "View in" link sits under the outcome text on an executed card', async ({ page }) => {
    const line = state(page, 'confirm-card-book-executed').locator('output')
    const text = (await line.locator('p').boundingBox())!
    const link = (await line.getByRole('link', { name: 'View in Time off' }).boundingBox())!
    expect(link.y).toBeGreaterThanOrEqual(text.y + text.height - 1)
  })

  test('source chips wrap onto a second row, and none runs past its card', async ({ page }) => {
    const chips = state(page, 'confirm-card-holiday-pending').locator('[data-slot="rule-chip"]')
    expect(await chips.count()).toBeGreaterThanOrEqual(2)
    const first = (await chips.nth(0).boundingBox())!
    const second = (await chips.nth(1).boundingBox())!
    expect(second.y).toBeGreaterThanOrEqual(first.y + first.height)
    for (const id of CONFIRM_IDS) {
      const section = state(page, id)
      const card = await section.locator('[data-slot="confirm-card"]').boundingBox()
      for (const chip of await section.locator('[data-slot="rule-chip"]').all()) {
        const box = (await chip.boundingBox())!
        expect(box.x + box.width, id).toBeLessThanOrEqual(card!.x + card!.width)
      }
    }
  })
})
