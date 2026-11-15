import { expect, test } from '../fixtures'
import {
  focusRingShows,
  focusView,
  motionFindings,
  reflowFindings,
  targetSizeFindings,
  textSpacingFindings,
} from './checks'

// Each audit check, proved on a small page of its own: it passes a clean page and catches a planted
// failure. These pages are set with `page.setContent`, so no sandbox starts and nothing reaches the
// API; the whole file takes a few seconds. A check that can't fail proves nothing, so this file is
// each check's lasting mutation proof.

const page320 = { viewport: { width: 320, height: 640 } }

test.describe('reflow at 320 px', () => {
  test.use(page320)

  test('passes text that wraps and a wide table in its own scrolling region', async ({ page }) => {
    await page.setContent(`
      <main>
        <p>Words that wrap at any width, as long as the page lets them.</p>
        <div style="overflow-x: auto"><table style="width: 900px"><tr><td>wide</td></tr></table></div>
      </main>`)
    expect(await reflowFindings(page)).toEqual([])
  })

  test('catches a box wider than the window', async ({ page }) => {
    await page.setContent(`<main><div id="wide" style="width: 400px">too wide</div></main>`)
    const found = await reflowFindings(page)
    expect(found.join('\n')).toContain('the page scrolls sideways')
    expect(found.join('\n')).toContain('div#wide')
  })

  test('catches a box a clipping wrapper cuts off, as the app’s sheet would (it clips, not scrolls)', async ({
    page,
  }) => {
    await page.setContent(`
      <main style="overflow: clip"><div id="cut" style="width: 400px">cut off</div></main>`)
    const found = await reflowFindings(page)
    expect(found.join('\n')).not.toContain('the page scrolls sideways')
    expect(found.join('\n')).toContain('div#cut')
  })

  test('passes text a label truncates by design, and text only screen readers get', async ({
    page,
  }) => {
    await page.setContent(`
      <main style="overflow: clip">
        <p style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; width: 300px">
          A long label <mark>with a highlight far past the end of the window</mark> and more words</p>
        <p style="overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; width: 300px">
          <span style="white-space: nowrap">a clamped line that runs on far past the window's edge</span></p>
        <span style="position: absolute; left: 330px; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%)">, source 1</span>
      </main>`)
    expect(await reflowFindings(page)).toEqual([])
  })

  test('catches a wide box whose wrapper, also too wide, has no height of its own', async ({
    page,
  }) => {
    await page.setContent(`
      <main><div style="width: 400px; height: 0"><div id="inner" style="width: 400px; position: absolute">wide</div></div></main>`)
    expect((await reflowFindings(page)).join('\n')).toContain('div#inner')
  })

  test('checks only inside the region it is given', async ({ page }) => {
    await page.setContent(`
      <section id="a"><div id="wide-a" style="width: 400px">a</div></section>
      <section id="b"><p>b</p></section>`)
    expect((await reflowFindings(page, page.locator('#a'))).join('\n')).toContain('div#wide-a')
    expect(await reflowFindings(page, page.locator('#b'))).toEqual([])
  })
})

test.describe('text spacing', () => {
  test('passes text in boxes that grow with it', async ({ page }) => {
    await page.setContent(`<main><p>A paragraph</p><button>Ask</button></main>`)
    expect(await textSpacingFindings(page)).toEqual([])
  })

  test('catches a one-line box whose fixed height clips the taller line', async ({ page }) => {
    // 20 px high fits a 20 px line; 1.4.12's line height of 1.5 makes the line 24 px.
    await page.setContent(`
      <main style="font: 16px sans-serif">
        <div id="fixed" style="height: 20px; line-height: 20px; overflow: hidden">Fits today</div>
      </main>`)
    expect(await textSpacingFindings(page)).toEqual([
      'div#fixed "Fits today" is clipped by its box (4 px)',
    ])
  })

  test('says when the words spill out of a fixed-height box', async ({ page }) => {
    await page.setContent(`
      <main style="font: 16px sans-serif">
        <div id="spill" style="height: 20px; line-height: 20px">Fits today</div>
      </main>`)
    expect(await textSpacingFindings(page)).toEqual([
      'div#spill "Fits today" spills out of its box (4 px)',
    ])
  })

  test('ignores a label the design already truncates', async ({ page }) => {
    await page.setContent(`
      <main style="font: 16px sans-serif">
        <div style="width: 60px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis">
          A label far too long for its box
        </div>
      </main>`)
    expect(await textSpacingFindings(page)).toEqual([])
  })

  test('leaves the page as it was', async ({ page }) => {
    await page.setContent(`<main><p id="p">A paragraph</p></main>`)
    const before = await page.locator('#p').evaluate((el) => getComputedStyle(el).letterSpacing)
    await textSpacingFindings(page)
    expect(await page.locator('#p').evaluate((el) => getComputedStyle(el).letterSpacing)).toBe(
      before,
    )
  })
})

test.describe('reduced motion', () => {
  test('passes a still page', async ({ page }) => {
    await page.setContent(`<main><p>Still</p></main>`)
    expect(await motionFindings(page)).toEqual([])
  })

  test('catches an animation that runs', async ({ page }) => {
    await page.setContent(`<main><div id="spin">Turning</div></main>`)
    await page.locator('#spin').evaluate((el) => {
      el.animate([{ transform: 'rotate(0)' }, { transform: 'rotate(1turn)' }], {
        duration: 10_000,
        iterations: Infinity,
      })
    })
    expect((await motionFindings(page)).join('\n')).toContain('div#spin')
  })
})

test.describe('target size', () => {
  test('passes 24 px targets, a small one with room, and a link in a sentence', async ({
    page,
  }) => {
    await page.setContent(`
      <main style="font: 14px sans-serif">
        <button style="width: 24px; height: 24px; padding: 0">A</button>
        <button style="width: 16px; height: 16px; padding: 0; margin-left: 40px">B</button>
        <p>Read <a href="#x">the handbook</a> first.</p>
      </main>`)
    expect(await targetSizeFindings(page)).toEqual([])
  })

  test('exempts a small marker drawn inline-flex inside a sentence', async ({ page }) => {
    await page.setContent(`
      <main style="font: 14px sans-serif">
        <p>Sick time is paid<button style="display: inline-flex; width: 16px; height: 16px; padding: 0"
          >1</button><button style="display: inline-flex; width: 16px; height: 16px; padding: 0"
          >2</button>.</p>
      </main>`)
    expect(await targetSizeFindings(page)).toEqual([])
  })

  test('catches two small targets side by side', async ({ page }) => {
    await page.setContent(`
      <main>
        <button id="one" style="width: 16px; height: 16px; padding: 0; margin: 0">1</button><button
          id="two" style="width: 16px; height: 16px; padding: 0; margin: 0">2</button>
      </main>`)
    const found = (await targetSizeFindings(page)).join('\n')
    expect(found).toContain('button#one')
    expect(found).toContain('button#two')
  })

  test('catches a small target whose circle reaches a long, thin neighbor', async ({ page }) => {
    // Centers 46 px apart, but the 16 px button's 24 px circle reaches the 20 px wide toggle 2 px away.
    await page.setContent(`
      <main style="position: relative">
        <button id="icon" style="position: absolute; left: 0; top: 0; width: 16px; height: 16px; padding: 0">i</button>
        <button id="tall" style="position: absolute; left: 18px; top: 0; width: 20px; height: 100px; padding: 0">t</button>
      </main>`)
    expect((await targetSizeFindings(page)).join('\n')).toContain('button#icon')
  })
})

test.describe('focus not obscured', () => {
  test('sees a focused button in the open', async ({ page }) => {
    await page.setContent(`<main><button id="b">Show your work</button></main>`)
    await page.locator('#b').focus()
    expect((await focusView(page)).shown).toBe(1)
  })

  test('sees a focused button entirely under a sticky bar as hidden', async ({ page }) => {
    await page.setContent(`
      <main style="height: 2000px">
        <div style="position: fixed; z-index: 10; bottom: 0; left: 0; right: 0; height: 120px; background: white">
          Composer
        </div>
        <button id="b" style="position: absolute; top: 560px">Show your work</button>
      </main>`)
    await page.setViewportSize({ width: 800, height: 640 })
    await page.locator('#b').focus()
    expect((await focusView(page)).shown).toBe(0)
  })

  test('sees a half-covered button as partly shown', async ({ page }) => {
    await page.setContent(`
      <main style="height: 2000px">
        <div style="position: fixed; z-index: 10; bottom: 0; left: 0; right: 0; height: 100px; background: white">
          Composer
        </div>
        <button id="b" style="position: absolute; top: 520px; height: 40px">Show your work</button>
      </main>`)
    await page.setViewportSize({ width: 800, height: 640 })
    await page.locator('#b').focus()
    const { shown } = await focusView(page)
    expect(shown).toBeGreaterThan(0)
    expect(shown).toBeLessThan(1)
  })
})

test.describe('focus ring', () => {
  const RING = `<style>
    :root { --color-focus-ring: #5b2a52 }
    :focus-visible { outline: 2px solid var(--color-focus-ring) }
  </style>`

  test('sees the outline ring the app draws on `:focus-visible`', async ({ page }) => {
    await page.setContent(`${RING}<main><button>Ask</button></main>`)
    await page.keyboard.press('Tab')
    expect(await focusRingShows(page)).toBe(true)
  })

  test('doesn’t take a shadow the control has at rest for a ring', async ({ page }) => {
    await page.setContent(`${RING}
      <style>.card { box-shadow: 0 1px 2px rgb(0 0 0 / 0.2) } .card:focus-visible { outline: none }</style>
      <main><button class="card">Open</button></main>`)
    await page.keyboard.press('Tab')
    expect(await focusRingShows(page)).toBe(false)
  })

  test('sees the text box’s ring: its wrapper’s halo in the ring’s color, after its transition', async ({
    page,
  }) => {
    await page.setContent(`${RING}
      <style>
        textarea:focus-visible { outline: none }
        .field { box-shadow: 0 1px 2px rgb(0 0 0 / 0.05); transition: box-shadow 0.15s, border-color 0.15s; border: 1px solid #7f8c93 }
        .field:focus-within { border-color: var(--color-focus-ring); box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-focus-ring) 18%, transparent) }
      </style>
      <main><div class="field"><textarea aria-label="Ask"></textarea></div></main>`)
    await page.keyboard.press('Tab')
    expect(await focusRingShows(page)).toBe(true)
  })

  test('sees a ring drawn as a shadow in the ring’s color', async ({ page }) => {
    await page.setContent(`${RING}
      <style>.halo:focus-visible { outline: none; box-shadow: 0 0 0 2px var(--color-focus-ring) }</style>
      <main><button class="halo">Open</button></main>`)
    await page.keyboard.press('Tab')
    expect(await focusRingShows(page)).toBe(true)
  })
})
