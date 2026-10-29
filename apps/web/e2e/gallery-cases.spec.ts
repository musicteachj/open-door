import { expect, test } from '@playwright/test'
import { GALLERY_STATE_IDS } from './gallery-ids'
import {
  expectNoViolationsIn,
  expectSectionHeadings,
  galleryState as state,
  holdKey,
  openGallery,
  statesPastEdge,
} from './helpers'

// The case button, form, sent line, and limit line (screen 11) in a real browser: axe on every
// state, the live panel by keyboard, and the layout at 1440 and 390 px.

const CASE_IDS = GALLERY_STATE_IDS.slice(
  GALLERY_STATE_IDS.indexOf('case-sensitive-offer'),
  GALLERY_STATE_IDS.indexOf('case-page-limit') + 1,
)

const HR_IDS = GALLERY_STATE_IDS.slice(
  GALLERY_STATE_IDS.indexOf('case-list-empty'),
  GALLERY_STATE_IDS.indexOf('case-detail-own') + 1,
)

const DIALOG_HOSTS = {
  'case-dialog-review': 'Open the start review dialog',
  'case-dialog-close': 'Open the close case dialog',
}

test.beforeEach(async ({ page }) => {
  await openGallery(page)
})

test('every case state has its own heading', async ({ page }) => {
  await expectSectionHeadings(page, CASE_IDS)
  for (const id of CASE_IDS) await expect(page.locator(`h3#${id}`)).toHaveCount(1)
})

test('no case state has accessibility violations', async ({ page }) => {
  test.setTimeout(120_000)
  await expectNoViolationsIn(page, CASE_IDS)
})

test('the live panel opens, returns focus on Not now, shows errors, and sends', async ({
  page,
}) => {
  const live = state(page, 'case-sensitive-offer')
  const open = live.getByRole('button', { name: 'Open a confidential case' })
  await open.click()
  await expect(live.getByRole('heading', { name: 'Open a confidential case' })).toBeFocused()
  await live.getByRole('button', { name: 'Not now' }).click()
  await expect(open).toBeFocused()

  await open.click()
  await live.getByRole('textbox', { name: 'Your words' }).fill('')
  await live.getByRole('button', { name: 'Send to HR' }).click()
  await expect(live.getByText('Choose what this is about.')).toBeVisible()
  await expect(live.getByText('Add your words before sending.')).toBeVisible()
  await expect(live.getByRole('radio').first()).toBeFocused()

  await live.getByRole('radio', { name: 'Pay concern' }).click()
  await live.getByRole('textbox', { name: 'Your words' }).fill('My pay was short.')
  await live.getByRole('button', { name: 'Send to HR' }).click()
  const sent = live.getByRole('status')
  await expect(sent).toBeFocused()
  await expect(sent).toContainText('Sent to HR. HR replies by Wednesday, October 28.')
  await page.keyboard.press('Tab')
  await expect(live.getByRole('link', { name: 'View in My cases' })).toBeFocused()
})

test('the form tabs through the choices, the words, the links, Send, and Not now', async ({
  page,
}) => {
  const form = state(page, 'case-form-open')
  await form.getByRole('radio').first().focus()
  const order: string[] = []
  for (let i = 0; i < 5; i += 1) {
    await page.keyboard.press('Tab')
    order.push(
      await page.evaluate(() => {
        const el = document.activeElement!
        return el.tagName === 'TEXTAREA' ? 'words' : (el.textContent ?? '').trim()
      }),
    )
  }
  expect(order).toEqual(['words', 'call 911', 'call or text 988', '1-800-555-0137', 'Send to HR'])
})

test('the band reaches the panel edges, with a confidential border on top', async ({ page }) => {
  const panel = state(page, 'case-form-open').locator('[data-slot="escalation-panel"]')
  const band = state(page, 'case-form-open').locator('[data-slot="case-form"]')
  const outer = (await panel.boundingBox())!
  const inner = (await band.boundingBox())!
  // The panel has a 1 px border.
  expect(Math.abs(inner.x - (outer.x + 1))).toBeLessThanOrEqual(1)
  expect(Math.abs(inner.width - (outer.width - 2))).toBeLessThanOrEqual(1)
})

test.describe('at 1440 px', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test('the choices sit in two columns, 44 px tall, and the buttons side by side', async ({
    page,
  }) => {
    const form = state(page, 'case-form-open')
    const radios = form.getByRole('radio')
    const boxes = await Promise.all((await radios.all()).map((r) => r.boundingBox()))
    expect(boxes[0]!.y).toBeCloseTo(boxes[1]!.y, 0)
    expect(boxes[2]!.y).toBeGreaterThan(boxes[0]!.y + 40)
    for (const box of boxes) expect(box!.height).toBeGreaterThanOrEqual(44)
    const send = (await form.getByRole('button', { name: 'Send to HR' }).boundingBox())!
    const later = (await form.getByRole('button', { name: 'Not now' }).boundingBox())!
    expect(Math.abs(send.y - later.y)).toBeLessThanOrEqual(1)
    expect(later.x).toBeGreaterThan(send.x)
  })

  test('an error sits beside the counter, which stays right-aligned', async ({ page }) => {
    const form = state(page, 'case-form-errors')
    const error = (await form.getByText(/looks like a Social Security/).boundingBox())!
    const count = (await form.getByText('81 of 4,000 characters').boundingBox())!
    expect(Math.abs(error.y - count.y)).toBeLessThanOrEqual(2)
    expect(count.x).toBeGreaterThan(error.x + error.width - 1)
  })
})

test.describe('at 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('nothing in the case states scrolls sideways', async ({ page }) => {
    await expect(page.locator('h3#case-form-open')).toBeAttached()
    expect
      .soft(
        await page.evaluate(() => document.documentElement.scrollWidth),
        'the page is wider than the window',
      )
      .toBeLessThanOrEqual(390)
    expect
      .soft(await statesPastEdge(page, CASE_IDS, 390), 'states with content past the edge')
      .toEqual([])
  })

  test('the choices stack in one column and the buttons stack full width, Send first', async ({
    page,
  }) => {
    const form = state(page, 'case-form-open')
    const boxes = await Promise.all(
      (await form.getByRole('radio').all()).map((r) => r.boundingBox()),
    )
    for (const [i, box] of boxes.entries()) {
      expect(Math.abs(box!.x - boxes[0]!.x), `choice ${i}`).toBeLessThanOrEqual(1)
      expect(Math.abs(box!.width - boxes[0]!.width), `choice ${i}`).toBeLessThanOrEqual(1)
    }
    const send = (await form.getByRole('button', { name: 'Send to HR' }).boundingBox())!
    const later = (await form.getByRole('button', { name: 'Not now' }).boundingBox())!
    expect(later.y).toBeGreaterThanOrEqual(send.y + send.height)
    expect(Math.abs(send.width - later.width)).toBeLessThanOrEqual(1)
    expect(Math.abs(send.x - later.x)).toBeLessThanOrEqual(1)
  })

  test('the counter stays right-aligned, under an error that wraps above it', async ({ page }) => {
    const form = state(page, 'case-form-errors')
    const error = (await form.getByText(/looks like a Social Security/).boundingBox())!
    const count = (await form.getByText('81 of 4,000 characters').boundingBox())!
    expect(count.y).toBeGreaterThanOrEqual(error.y + error.height - 1)
    const textarea = (await form.getByRole('textbox', { name: 'Your words' }).boundingBox())!
    expect(Math.abs(count.x + count.width - (textarea.x + textarea.width))).toBeLessThanOrEqual(2)
  })
})

// ----- Batch B: My cases, HR's queue, and the detail -----

test.describe('My cases, the queue, and the detail', () => {
  test('every state has its own heading', async ({ page }) => {
    await expectSectionHeadings(page, HR_IDS)
  })

  test('no state has accessibility violations', async ({ page }) => {
    test.setTimeout(180_000)
    await expectNoViolationsIn(
      page,
      HR_IDS,
      Object.fromEntries(
        Object.entries(DIALOG_HOSTS).map(([id, button]) => [
          id,
          { button, role: 'alertdialog' as const },
        ]),
      ),
    )
  })

  test('the queue filter is one tab stop, and the arrow keys change it', async ({ page }) => {
    const queue = state(page, 'case-queue-open')
    await queue.getByRole('radio', { name: 'Open' }).focus()
    await page.keyboard.press('Tab')
    await expect(queue.getByRole('link').first()).toBeFocused()
    await page.keyboard.press('Shift+Tab')
    await expect(queue.getByRole('radio', { name: 'Open' })).toBeFocused()
    await holdKey(page, 'ArrowRight', () =>
      expect(queue.getByRole('radio', { name: 'New' })).toBeChecked(),
    )
    await expect(queue.getByRole('link')).toHaveCount(3)
  })

  test('a queue row is named by its facts, in order', async ({ page }) => {
    await expect(
      state(page, 'case-queue-open').getByRole('link', {
        name: 'Priya Raman, Visual Merchandiser, Oakland store. Harassment or discrimination. Sent Mon, Oct 26. Reply due Wed, Oct 28. New.',
      }),
    ).toHaveAttribute('href', '/cases/case-priya')
  })

  test('an overdue reply and the crisis fact are neutral ink, never red', async ({ page }) => {
    const facts = state(page, 'case-queue-facts')
    const color = (locator: ReturnType<typeof facts.getByText>) =>
      locator.evaluate((el) => getComputedStyle(el).color)
    const body = await facts.getByText('Reply was due Mon, Oct 26').evaluate((el) => {
      return getComputedStyle(el).color
    })
    const ink = await facts
      .getByText('Reply due Wed, Oct 28')
      .evaluate((el) => getComputedStyle(el).color)
    expect(body).toBe(ink)
    const fact = await color(
      facts.getByText('The safety check routed this message to crisis text.'),
    )
    const sent = await color(facts.getByText('Thu, Oct 22'))
    expect(fact).toBe(sent)
  })

  test('the locked actions are focusable and aria-disabled, and do nothing', async ({ page }) => {
    const frame = state(page, 'case-detail-new')
    const start = frame.getByRole('button', { name: 'Start review' })
    await expect(start).toHaveAttribute('aria-disabled', 'true')
    await start.focus()
    await expect(start).toBeFocused()
    // Playwright treats aria-disabled as not enabled, so the press is forced.
    await start.click({ force: true })
    await page.keyboard.press('Enter')
    await expect(page.getByRole('alertdialog')).toHaveCount(0)
    await expect(start).toHaveAccessibleDescription(
      'Read Priya’s words before changing the status.',
    )
  })

  test('showing the words adds exactly one timeline row, and hiding adds none', async ({
    page,
  }) => {
    const frame = state(page, 'case-detail-revealed')
    const rows = frame.locator('[data-slot="case-timeline"] li')
    await expect(rows).toHaveCount(4)
    const hide = frame.getByRole('button', { name: 'Hide Priya’s words' })
    await expect(hide).toHaveAttribute('aria-expanded', 'true')
    await hide.click()
    await expect(rows).toHaveCount(4)
    const show = frame.getByRole('button', { name: 'Show Priya’s words' })
    await expect(show).toBeFocused()
    await expect(show).toHaveAttribute('aria-expanded', 'false')
    await show.click()
    await expect(rows).toHaveCount(5)
    await expect(frame.getByRole('button', { name: 'Hide Priya’s words' })).toBeFocused()
    // The new row is announced politely, once.
    await expect(page.locator('[data-slot="announcer"] [aria-live="polite"]')).toHaveText(
      'Added to the timeline: Dana Whitfield read Priya’s words',
    )
  })

  for (const [id, button] of Object.entries(DIALOG_HOSTS)) {
    test(`${id}: focus starts on Cancel, and Escape returns it to the opener`, async ({ page }) => {
      const frame = state(page, id)
      const opener = frame.getByRole('button', { name: button })
      await opener.click()
      const dialog = page.getByRole('alertdialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeFocused()
      await page.keyboard.press('Escape')
      await expect(dialog).toHaveCount(0)
      await expect(opener).toBeFocused()
    })
  }

  test('the status dialogs open from the live buttons, and Cancel returns focus to them', async ({
    page,
  }) => {
    const frame = state(page, 'case-detail-revealed')
    const start = frame.getByRole('button', { name: 'Start review' })
    await start.click()
    const dialog = page.getByRole('alertdialog', { name: 'Start review of this case?' })
    await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeFocused()
    await dialog.getByRole('button', { name: 'Cancel' }).click()
    await expect(start).toBeFocused()
    await start.click()
    await dialog.getByRole('button', { name: 'Start review' }).click()
    await expect(frame.getByRole('button', { name: 'Close case' })).toBeFocused()
    await expect(frame.getByText('In review since Mon, Oct 26')).toBeVisible()
    await frame.getByRole('button', { name: 'Close case' }).click()
    await page
      .getByRole('alertdialog', { name: 'Close this case?' })
      .getByRole('button', { name: 'Close case' })
      .click()
    await expect(frame.getByRole('heading', { level: 1 })).toBeFocused()
    await expect(frame.getByText('This case is closed.')).toBeVisible()
  })

  test.describe('at 1440 px', () => {
    test.use({ viewport: { width: 1440, height: 900 } })

    test('the detail is two columns: a 360 px timeline beside the main column, 40 px apart', async ({
      page,
    }) => {
      const frame = state(page, 'case-detail-new')
      const timeline = (await frame.locator('[data-slot="case-timeline"]').boundingBox())!
      const person = (await frame.locator('[data-slot="case-person-card"]').boundingBox())!
      expect(Math.abs(timeline.width - 360)).toBeLessThanOrEqual(1)
      expect(Math.abs(timeline.x - (person.x + person.width + 40))).toBeLessThanOrEqual(1)
    })

    test('the queue is a 64 px minimum row with the design’s header', async ({ page }) => {
      const queue = state(page, 'case-queue-open')
      const row = (await queue.getByRole('link').first().boundingBox())!
      expect(row.height).toBeGreaterThanOrEqual(64)
      await expect(queue.getByText('Person', { exact: true })).toBeVisible()
    })

    test('My cases rows use 1fr, 248 px, and 176 px columns', async ({ page }) => {
      const row = state(page, 'case-list-rows').getByRole('listitem').first()
      const columns = await row.evaluate((el) => getComputedStyle(el).gridTemplateColumns)
      const widths = columns.split(' ').map(Number.parseFloat)
      expect(widths.slice(1)).toEqual([248, 176])
    })
  })

  test.describe('at 390 px', () => {
    test.use({ viewport: { width: 390, height: 844 } })

    test('nothing sideways, in any state or on the page', async ({ page }) => {
      await expect(page.locator('h3#case-list-empty')).toBeAttached()
      expect
        .soft(await page.evaluate(() => document.documentElement.scrollWidth))
        .toBeLessThanOrEqual(390)
      const QUEUES = [
        'case-queue-open',
        'case-queue-closed',
        'case-queue-empty',
        'case-queue-facts',
      ]
      expect
        .soft(
          await statesPastEdge(
            page,
            HR_IDS.filter((id) => !QUEUES.includes(id)),
            390,
          ),
          'states with content past the edge',
        )
        .toEqual([])
      // The filter scrolls sideways inside its own control, so what it holds is left out.
      for (const id of QUEUES) {
        const past = await state(page, id).evaluate(
          (el) =>
            [...el.querySelectorAll<HTMLElement>('*')].filter(
              (c) => c.getBoundingClientRect().right > 391 && !c.closest('[role="radiogroup"]'),
            ).length,
        )
        expect.soft(past, `${id} has content past the edge`).toBe(0)
      }
      const group = state(page, 'case-queue-open').getByRole('radiogroup')
      const groupBox = (await group.boundingBox())!
      expect(groupBox.x + groupBox.width).toBeLessThanOrEqual(390)
    })

    test('the queue stacks: no header, no sent date, the reply line left and the badge right', async ({
      page,
    }) => {
      const queue = state(page, 'case-queue-open')
      await expect(queue.getByText('Person', { exact: true })).toBeHidden()
      const link = queue.getByRole('link').first()
      await expect(link.getByText('Thu, Oct 22')).toBeHidden()
      const reply = (await link.getByText('Reply due today').boundingBox())!
      const badge = (await link.getByText('New').boundingBox())!
      expect(Math.abs(reply.y - badge.y)).toBeLessThan(12)
      expect(badge.x).toBeGreaterThan(reply.x + reply.width)
    })

    test('the status buttons are full width, primary first', async ({ page }) => {
      const frame = state(page, 'case-detail-revealed')
      const start = (await frame.getByRole('button', { name: 'Start review' }).boundingBox())!
      const close = (await frame.getByRole('button', { name: 'Close case' }).boundingBox())!
      expect(close.y).toBeGreaterThanOrEqual(start.y + start.height)
      expect(Math.abs(start.width - close.width)).toBeLessThanOrEqual(1)
    })

    test('a status dialog is full width with 16 px margins, Cancel under the primary', async ({
      page,
    }) => {
      await state(page, 'case-dialog-close').getByRole('button').click()
      const dialog = page.getByRole('alertdialog')
      const box = (await dialog.boundingBox())!
      expect(Math.abs(box.x - 16)).toBeLessThanOrEqual(1)
      expect(Math.abs(box.width - (390 - 32))).toBeLessThanOrEqual(1)
      const primary = (await dialog.getByRole('button', { name: 'Close case' }).boundingBox())!
      const cancel = (await dialog.getByRole('button', { name: 'Cancel' }).boundingBox())!
      expect(cancel.y).toBeGreaterThanOrEqual(primary.y + primary.height)
      await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeFocused()
    })
  })
})
