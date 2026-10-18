import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { GALLERY_STATE_IDS } from './gallery-ids'
import { AXE_TAGS } from './helpers'

// The conversation section of the gallery in a real browser: axe on every state, the pieces that
// need a real browser (Stop, focus, aria-expanded), and 390 px.

const CONVERSATION_IDS = GALLERY_STATE_IDS.filter((id) => id.startsWith('conversation-'))

const state = (page: Page, id: string) => page.locator(`section[aria-labelledby="${id}"]`)

/** The marker a passage opens from, in the source panel state: the third one, "Source 1". */
const sourceMarker = (page: Page) =>
  state(page, 'conversation-source-panel')
    .getByRole('button', { name: 'Source 1: Handbook CA-4.3, California addendum' })
    .nth(2)
const passagePanel = (page: Page) =>
  state(page, 'conversation-source-panel').getByRole('complementary', { name: 'Handbook passage' })

test.beforeEach(async ({ page }) => {
  await page.goto('/gallery')
  await expect(
    page.getByRole('heading', { level: 1, name: 'Open Door component gallery' }),
  ).toBeVisible()
})

test('the conversation section has every state under its own heading', async ({ page }) => {
  expect(CONVERSATION_IDS).toHaveLength(24)
  for (const id of CONVERSATION_IDS) await expect(page.locator(`h3#${id}`)).toHaveCount(1)
})

for (const id of CONVERSATION_IDS) {
  test(`${id} has no accessibility violations`, async ({ page }) => {
    const results = await new AxeBuilder({ page })
      .withTags(AXE_TAGS)
      .include(`section[aria-labelledby="${id}"]`)
      .analyze()
    expect(results.violations).toEqual([])
  })
}

test('the source panel state, with its passage open, has no accessibility violations', async ({
  page,
}) => {
  await sourceMarker(page).scrollIntoViewIfNeeded()
  await sourceMarker(page).click()
  await expect(passagePanel(page)).toBeVisible()
  const results = await new AxeBuilder({ page })
    .withTags(AXE_TAGS)
    .include('section[aria-labelledby="conversation-source-panel"]')
    .analyze()
  expect(results.violations).toEqual([])
})

test('pressing a marker opens its passage, marks only that marker, and moves focus to the title', async ({
  page,
}) => {
  const marker = sourceMarker(page)
  await marker.scrollIntoViewIfNeeded()
  await expect(marker).toHaveAttribute('aria-expanded', 'false')
  await marker.click()
  await expect(passagePanel(page)).toBeVisible()
  await expect(marker).toHaveAttribute('aria-expanded', 'true')
  await expect(passagePanel(page).getByRole('heading', { name: 'Sick leave' })).toBeFocused()
  const markers = state(page, 'conversation-source-panel').getByRole('button', {
    name: /^Source \d: /,
    expanded: true,
  })
  // Two are active: the marker for the open passage, and its section's chip (a chip shows open
  // while any passage of its section is). The other markers and the other section's chip are not.
  await expect(markers).toHaveCount(2)
  await expect(
    state(page, 'conversation-source-panel')
      .getByRole('list', { name: 'Sources' })
      .getByRole('button', { name: /^Source 1: /, expanded: true }),
  ).toHaveCount(1)
  // The close button puts focus back on the marker.
  await passagePanel(page).getByRole('button', { name: 'Close passage' }).click()
  await expect(passagePanel(page)).toBeHidden()
  await expect(marker).toBeFocused()
  await expect(marker).toHaveAttribute('aria-expanded', 'false')
})

test('"Show your work" toggles aria-expanded, and keeps focus on its button', async ({ page }) => {
  const section = state(page, 'conversation-cited-answer')
  const toggle = section.getByRole('button', { name: 'Show your work' })
  await toggle.scrollIntoViewIfNeeded()
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-expanded', 'true')
  await expect(section.getByText('Safety check: no concerns')).toBeVisible()
  await expect(toggle).toBeFocused()
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await expect(section.getByText('Safety check: no concerns')).toBeHidden()
})

test('pressing No moves focus into the reason box, and Cancel puts it back on No', async ({
  page,
}) => {
  const section = state(page, 'conversation-cited-answer')
  const no = section.getByRole('button', { name: 'No' })
  await no.scrollIntoViewIfNeeded()
  await no.click()
  await expect(section.getByRole('textbox', { name: /What was wrong/ })).toBeFocused()
  await section.getByRole('button', { name: 'Cancel' }).click()
  await expect(no).toBeFocused()
  await expect(section.getByRole('textbox', { name: /What was wrong/ })).toBeHidden()
})

test('pressing Yes moves focus to the thank-you line', async ({ page }) => {
  const section = state(page, 'conversation-cited-answer')
  await section.getByRole('button', { name: 'Yes' }).click()
  await expect(section.getByText('Thanks for the feedback.')).toBeFocused()
})

test('Stop ends the stream without sending the draft, and the draft stays in the box', async ({
  page,
}) => {
  const section = state(page, 'conversation-send-error')
  const frame = section.locator('[data-submit-count]')
  const box = section.getByRole('textbox', { name: 'Ask Open Door' })
  await box.scrollIntoViewIfNeeded()
  await expect(frame).toHaveAttribute('data-submit-count', '0')
  await expect(section.getByRole('alert')).toHaveText("I'm still answering your last question.")

  // A typed draft, as a person would leave one, then a real click on Stop. The click re-renders the
  // composer (the stream has ended) before the browser runs the click's default action, and that
  // action must not be a submit.
  await box.fill('A different question, typed while it streams')
  await section.getByRole('button', { name: 'Stop' }).click()

  await expect(section.getByRole('button', { name: 'Ask', exact: true })).toBeVisible()
  await expect(section.getByText('Stopped', { exact: true })).toBeVisible()
  await expect(box).toHaveValue('A different question, typed while it streams')
  await expect(box).toBeFocused()
  // Give a stray submit time to land before the count is read.
  await page.waitForTimeout(250)
  await expect(frame).toHaveAttribute('data-submit-count', '0')
})

test('Enter while streaming sends nothing, and Ask sends the draft once the stream is over', async ({
  page,
}) => {
  const section = state(page, 'conversation-send-error')
  const frame = section.locator('[data-submit-count]')
  const box = section.getByRole('textbox', { name: 'Ask Open Door' })
  await box.scrollIntoViewIfNeeded()
  await box.press('Enter')
  await expect(frame).toHaveAttribute('data-submit-count', '0')
  await section.getByRole('button', { name: 'Stop' }).click()
  await section.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(frame).toHaveAttribute('data-submit-count', '1')
})

test('the budget composers are disabled, and the Handbook and Directory links under them stay', async ({
  page,
}) => {
  const section = state(page, 'conversation-budget-sandbox')
  const box = section.getByRole('textbox', { name: 'Ask Open Door' })
  await box.scrollIntoViewIfNeeded()
  await expect(box).toBeDisabled()
  await expect(section.getByRole('button', { name: 'Ask', exact: true })).toBeDisabled()
  await expect(section.getByRole('link', { name: 'Handbook' })).toBeVisible()
  await expect(section.getByRole('link', { name: 'Directory' })).toBeVisible()
})

test('the 911 and 988 calls in the banners and panels are tel: links', async ({ page }) => {
  for (const id of ['conversation-budget-sandbox', 'conversation-budget-daily']) {
    const section = state(page, id)
    await expect(section.getByRole('link', { name: 'call 911' })).toHaveAttribute('href', 'tel:911')
    await expect(section.getByRole('link', { name: 'call or text 988' })).toHaveAttribute(
      'href',
      'tel:988',
    )
  }
  const unavailable = state(page, 'conversation-cant-answer')
  await expect(unavailable.getByRole('link', { name: 'call 911' })).toHaveAttribute(
    'href',
    'tel:911',
  )
  await expect(unavailable.getByRole('link', { name: 'call or text 988' })).toHaveAttribute(
    'href',
    'tel:988',
  )
})

test('the conversation column is the design 760 px measure, with the assistant capped at 680', async ({
  page,
}) => {
  const section = state(page, 'conversation-cited-answer')
  await section.scrollIntoViewIfNeeded()
  const thread = await section.locator('[data-slot="conversation-thread"]').boundingBox()
  const message = await section.locator('[data-slot="assistant-message"]').boundingBox()
  expect(thread!.width).toBe(760)
  expect(message!.width).toBe(680)
})

test('a conversation state is not wider than the gallery column by accident: it stays centered', async ({
  page,
}) => {
  const section = state(page, 'conversation-cited-answer')
  const frame = await section.locator('[data-slot="conversation-frame"]').boundingBox()
  const viewport = page.viewportSize()!
  expect(Math.abs(frame!.x + frame!.width / 2 - viewport.width / 2)).toBeLessThanOrEqual(8)
})

test('Retry follows the message of a mid-stream error on the same line', async ({ page }) => {
  const alert = state(page, 'conversation-error-midstream').getByRole('alert')
  await alert.scrollIntoViewIfNeeded()
  const text = await alert.locator('p').boundingBox()
  const retry = await alert.getByRole('button', { name: 'Retry' }).boundingBox()
  const message = await state(page, 'conversation-error-midstream')
    .locator('[data-slot="assistant-message"]')
    .boundingBox()
  const sameLine = Math.abs(retry!.y + retry!.height / 2 - (text!.y + text!.height / 2)) <= 12
  if (sameLine) {
    expect(retry!.x - (text!.x + text!.width)).toBeLessThanOrEqual(16)
  } else {
    // The API's text is long, so Retry wraps under it, at the text's own left edge.
    expect(retry!.x).toBeLessThanOrEqual(text!.x + 4)
  }
  // Not at the far end of the 680 px message.
  expect(retry!.x + retry!.width).toBeLessThan(message!.x + message!.width - 100)
})

test.describe('the docked composer', () => {
  const composerBox = (page: Page, id: string) =>
    state(page, id).getByRole('textbox', { name: 'Ask Open Door' })

  test('starts at one line, grows with its text to about four lines, then scrolls', async ({
    page,
  }) => {
    const box = composerBox(page, 'conversation-cited-answer')
    await box.scrollIntoViewIfNeeded()
    const one = (await box.boundingBox())!.height
    expect(one).toBeLessThan(70)
    await box.fill('one\ntwo')
    const two = (await box.boundingBox())!.height
    expect(two).toBeGreaterThan(one + 20)
    await box.fill('one\ntwo\nthree\nfour\nfive\nsix\nseven')
    const many = (await box.boundingBox())!.height
    expect(many).toBeLessThanOrEqual(141)
    expect(many).toBeGreaterThan(two)
    expect(await box.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true)
  })

  test('a draft near 2,000 characters shows about four lines and scrolls', async ({ page }) => {
    const box = composerBox(page, 'conversation-length-hint')
    await box.scrollIntoViewIfNeeded()
    expect((await box.boundingBox())!.height).toBeLessThanOrEqual(141)
    expect(await box.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true)
  })
})

test.describe('at 1440 px', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test('every frame is 810 px wide, the source-panel state included', async ({ page }) => {
    for (const id of CONVERSATION_IDS) {
      const frame = state(page, id).locator('[data-slot="conversation-frame"]')
      await frame.scrollIntoViewIfNeeded()
      expect((await frame.boundingBox())!.width, id).toBe(810)
    }
  })

  test('the source panel sits in its own 420 px frame below the conversation frame, on the same left edge', async ({
    page,
  }) => {
    await sourceMarker(page).scrollIntoViewIfNeeded()
    await sourceMarker(page).click()
    await expect(passagePanel(page)).toBeVisible()
    const section = state(page, 'conversation-source-panel')
    const frame = (await section.locator('[data-slot="conversation-frame"]').boundingBox())!
    const panel = (await section.locator('[data-slot="source-panel-frame"]').boundingBox())!
    expect(frame.width).toBe(810)
    expect(panel.width).toBe(420)
    expect(panel.y).toBeGreaterThanOrEqual(frame.y + frame.height)
    expect(panel.x).toBe(frame.x)
    expect(panel.x + panel.width).toBeLessThanOrEqual(1440)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      1440,
    )
  })

  test('the composer keeps its disclosure on one line beside Ask', async ({ page }) => {
    const section = state(page, 'conversation-cited-answer')
    const disclosure = section.getByText(/Open Door is an AI assistant/)
    await disclosure.scrollIntoViewIfNeeded()
    expect((await disclosure.boundingBox())!.height).toBeLessThan(24)
  })

  // The header row has almost no spare room at the 760 px measure, as in the design: on macOS the
  // retention line fits on one line with a fraction of a pixel left, and Linux draws the bold
  // button about 12 px wider, so there it wraps. Either is fine; what must hold everywhere is that
  // nothing overflows, the button and the pill stay whole, and the line takes at most two lines.
  test('the header row fits: the button and pill stay whole and the line wraps at most once', async ({
    page,
  }) => {
    const section = state(page, 'conversation-cited-answer')
    const header = section.locator('[data-slot="conversation-header"]')
    await header.scrollIntoViewIfNeeded()
    const overflow = await header.evaluate((row) => row.scrollWidth - row.clientWidth)
    expect(overflow).toBeLessThanOrEqual(0)
    const line = header.getByText('Conversations are deleted with your sandbox after 24 hours.')
    expect((await line.boundingBox())!.height).toBeLessThan(44)
    const button = header.getByRole('button', { name: 'Start a new conversation' })
    expect((await button.boundingBox())!.height).toBeLessThan(36)
    const pill = header.getByText(/Sandbox resets in/)
    expect((await pill.boundingBox())!.height).toBeLessThan(30)
  })
})

for (const width of [641, 700, 760, 900, 1000, 1280]) {
  test.describe(`at ${width} px`, () => {
    test.use({ viewport: { width, height: 900 } })

    test('no conversation state scrolls the page sideways, or sticks out of the window', async ({
      page,
    }) => {
      await sourceMarker(page).scrollIntoViewIfNeeded()
      await sourceMarker(page).click()
      await expect(passagePanel(page)).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
        width,
      )
      const out = await page.evaluate((w) => {
        const slots = '[data-slot="conversation-state"], [data-slot="source-panel-frame"]'
        return [...document.querySelectorAll(slots)].filter((el) => {
          const box = el.getBoundingClientRect()
          return box.left < -1 || box.right > w + 1
        }).length
      }, width)
      expect(out).toBe(0)
    })
  })
}

test.describe('at 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('nothing in the conversation section scrolls sideways', async ({ page }) => {
    await expect(page.locator('h3#conversation-cited-answer')).toBeAttached()
    // The source panel is open, so its sheet is measured too.
    await sourceMarker(page).scrollIntoViewIfNeeded()
    await sourceMarker(page).click()
    await expect(passagePanel(page)).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    for (const id of CONVERSATION_IDS) {
      const wide = await state(page, id).evaluate(
        (el) =>
          // Text clipped by a truncating ancestor (a source chip's label) is not sideways scroll.
          [...el.querySelectorAll<HTMLElement>('*')].filter(
            (child) =>
              child.getBoundingClientRect().right > 390 + 1 && child.closest('.truncate') === null,
          ).length,
      )
      expect(wide, `${id} has content past the right edge`).toBe(0)
    }
  })

  test('the header keeps "Start a new conversation" as an icon button, and the retention line moves under the composer', async ({
    page,
  }) => {
    const section = state(page, 'conversation-cited-answer')
    const button = section.getByRole('button', { name: 'Start a new conversation' })
    await button.scrollIntoViewIfNeeded()
    expect((await button.boundingBox())!.width).toBeLessThan(48)
    const line = section.getByText('Conversations are deleted with your sandbox after 24 hours.')
    await expect(line).toHaveCount(2)
    await expect(line.first()).toBeHidden()
    await expect(line.last()).toBeVisible()
  })

  test('the composer footer puts the disclosure above Ask, with Ask at the end', async ({
    page,
  }) => {
    const section = state(page, 'conversation-cited-answer')
    const disclosure = section.getByText(/Open Door is an AI assistant/)
    await disclosure.scrollIntoViewIfNeeded()
    const text = (await disclosure.boundingBox())!
    const ask = (await section.getByRole('button', { name: 'Ask', exact: true }).boundingBox())!
    const composer = (await section.locator('[data-slot="composer"]').boundingBox())!
    expect(text.y + text.height).toBeLessThanOrEqual(ask.y)
    expect(composer.x + composer.width - (ask.x + ask.width)).toBeLessThanOrEqual(16)
    // Three lines at most, not the four it had squeezed into.
    expect(text.height).toBeLessThanOrEqual(64)
  })

  test('"Sections retrieved" stacks each row: number and status above, the title full width', async ({
    page,
  }) => {
    const section = state(page, 'conversation-show-your-work')
    const row = section
      .locator('[data-slot="work-trace-panel"] li')
      .filter({ hasText: 'Cited as 1' })
    await row.scrollIntoViewIfNeeded()
    const [number, title, status] = await Promise.all(
      [0, 1, 2].map((i) => row.locator(':scope > span').nth(i).boundingBox()),
    )
    expect(title!.y).toBeGreaterThan(number!.y + number!.height - 4)
    expect(Math.abs(status!.y - number!.y)).toBeLessThanOrEqual(4)
    // The title has the row's width, so "Sick leave · California addendum" is one line.
    const rowBox = (await row.boundingBox())!
    expect(title!.width).toBeGreaterThan(rowBox.width - 4)
    expect(title!.height).toBeLessThanOrEqual(24)
  })

  test('the feedback reason form counts on one line, above Cancel and Send feedback', async ({
    page,
  }) => {
    const section = state(page, 'conversation-feedback-no')
    const counter = section.getByText('45 of 500 characters')
    await counter.scrollIntoViewIfNeeded()
    const count = (await counter.boundingBox())!
    const cancel = (await section.getByRole('button', { name: 'Cancel' }).boundingBox())!
    const send = (await section.getByRole('button', { name: 'Send feedback' }).boundingBox())!
    expect(count.height).toBeLessThanOrEqual(20)
    expect(count.y + count.height).toBeLessThanOrEqual(cancel.y)
    const form = (await section.locator('[data-slot="feedback-form"]').boundingBox())!
    // The buttons sit at the end of their row.
    expect(form.x + form.width - (send.x + send.width)).toBeLessThanOrEqual(20)
  })

  test('an email address breaks only after the @, never inside a part', async ({ page }) => {
    const link = state(page, 'conversation-not-found').getByRole('link', {
      name: 'dana.whitfield@juniperrow.example',
    })
    await link.scrollIntoViewIfNeeded()
    // The address as the browser lays it out: the line each character is on.
    const lines = await link.evaluate((el) => {
      const found: string[] = []
      let current = ''
      let top: number | null = null
      const range = document.createRange()
      const nodes = [...el.childNodes].filter((node): node is Text => node.nodeType === 3)
      for (const node of nodes) {
        for (let i = 0; i < node.length; i += 1) {
          range.setStart(node, i)
          range.setEnd(node, i + 1)
          const y = Math.round(range.getBoundingClientRect().top)
          if (top !== null && y !== top) {
            found.push(current)
            current = ''
          }
          top = y
          current += node.data[i]
        }
      }
      found.push(current)
      return found
    })
    expect(lines.join('')).toBe('dana.whitfield@juniperrow.example')
    for (const line of lines) {
      expect([
        'dana.whitfield@',
        'juniperrow.example',
        'dana.whitfield@juniperrow.example',
      ]).toContain(line)
    }
  })
})
