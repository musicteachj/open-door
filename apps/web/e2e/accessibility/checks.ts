import { expect, test, type Locator, type Page } from '@playwright/test'
import { focusedName } from '../helpers'

// The accessibility audit's own checks (Phase 8, Stage 8), for what axe doesn't measure: reflow at
// 320 px (WCAG 1.4.10), text spacing (1.4.12), reduced motion (2.3.3, and the app's own rule that
// nothing moves under `prefers-reduced-motion`), target size (2.5.8), and focus not obscured
// (2.4.11). Each one reads the page as it is now and returns what it found, as short readable
// lines, so a failing test names the element. checks.spec.ts proves each one catches a planted
// failure and passes a clean page; docs/ACCESSIBILITY.md says how they're used.

/**
 * Adds `window.__a11yDescribe` to the page once: a short name for an element in a finding (its
 * tag, id or slot, and its first words). Defined inside the page by a plain function, never by
 * `eval`, which the production image's Content Security Policy would refuse.
 */
async function installDescribe(page: Page) {
  await page.evaluate(() => {
    const w = window as unknown as { __a11yDescribe?: (el: Element) => string }
    w.__a11yDescribe ??= (el: Element) => {
      const slot = el.getAttribute('data-slot')
      const id = el.id ? `#${el.id}` : ''
      const label = el.getAttribute('aria-label')
      const text = (label ?? el.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 40)
      return `${el.tagName.toLowerCase()}${id}${slot ? `[${slot}]` : ''}${text ? ` "${text}"` : ''}`
    }
  })
}

/** Waits two frames, so a style change has been laid out. */
export const settle = (page: Page) =>
  page.evaluate(
    () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
  )

// ---------------------------------------------------------------------------------------------
// Reflow (1.4.10): at 320 CSS px wide nothing needs a sideways scroll, except content that scrolls
// in its own region (a data table in a `Scroller`) and text truncated by design. A wrapper that
// only clips doesn't count as a region: what it cuts off is lost. The app's sheet clips (for its rounded corners), so
// counting it would hide every finding inside the app.

/**
 * What reaches past the right edge of a 320 px window, outside any region that scrolls itself.
 * With `within`, only inside that element (one gallery state, say), and without the page's own
 * sideways scroll.
 */
export async function reflowFindings(page: Page, within?: Locator): Promise<string[]> {
  await installDescribe(page)
  const check = (scope: Element | null) => {
    const describe = (window as unknown as { __a11yDescribe: (el: Element) => string })
      .__a11yDescribe
    const found: string[] = []
    const root = document.documentElement
    const top = scope ?? document.body
    if (scope === null && root.scrollWidth > root.clientWidth) {
      found.push(`the page scrolls sideways (${root.scrollWidth} px in ${root.clientWidth})`)
    }
    const edge = root.clientWidth
    // A region of its own: one that scrolls sideways, or one that truncates its text by design
    // (an ellipsis or a line clamp; the full words are in the accessible name or a step away).
    const ownRegion = (el: Element) => {
      const style = getComputedStyle(el)
      if (/^(auto|scroll)$/.test(style.overflowX)) return true
      return (
        style.overflowX !== 'visible' &&
        (style.textOverflow === 'ellipsis' || style.webkitLineClamp !== 'none')
      )
    }
    // Elements already reported: their descendants past the edge are the same finding.
    const reported = new Set<Element>()
    for (const el of top.querySelectorAll('*')) {
      if (!(el instanceof HTMLElement) && !(el instanceof SVGSVGElement)) continue
      if (!el.checkVisibility({ visibilityProperty: true, opacityProperty: true })) continue
      const box = el.getBoundingClientRect()
      // A 1 px box is text for screen readers only (`sr-only`), which shows nothing.
      if (box.width <= 1 || box.height <= 1 || box.right <= edge + 1) continue
      let parent = el.parentElement
      let skip = false
      while (parent && parent !== top.parentElement) {
        if (reported.has(parent) || ownRegion(parent)) {
          skip = true
          break
        }
        parent = parent.parentElement
      }
      if (skip) continue
      reported.add(el)
      found.push(`${describe(el)} reaches ${Math.round(box.right)} px`)
    }
    return found
  }
  return within ? within.evaluate(check) : page.evaluate(check, null)
}

// ---------------------------------------------------------------------------------------------
// Text spacing (1.4.12): with the criterion's spacing applied, no text is lost. Measured as a
// difference: an element that overflows its box with the spacing but didn't without it. A label
// the design already truncates, with its full words in the accessible name, isn't a new loss.

export const TEXT_SPACING_CSS = `
  *, *::before, *::after {
    line-height: 1.5 !important;
    letter-spacing: 0.12em !important;
    word-spacing: 0.16em !important;
  }
  p { margin-bottom: 2em !important; }
`

/** The elements whose content overflows their box, by a mark the check puts on each. */
async function overflowing(page: Page, mark: string): Promise<number> {
  return page.evaluate((attribute) => {
    let count = 0
    for (const el of document.body.querySelectorAll<HTMLElement>('*')) {
      if (!el.checkVisibility({ visibilityProperty: true })) continue
      const style = getComputedStyle(el)
      if (style.display === 'inline' || style.display === 'contents') continue
      // A region that scrolls keeps its content reachable.
      if (/auto|scroll/.test(style.overflowX + style.overflowY)) continue
      // Only boxes that hold text of their own: a wrapper that overflows because a child does is
      // the child's finding.
      const ownText = [...el.childNodes].some(
        (n) => n.nodeType === Node.TEXT_NODE && (n.textContent ?? '').trim() !== '',
      )
      if (!ownText) continue
      // Screen-reader-only text is clipped on purpose.
      if (el.getBoundingClientRect().width <= 1) continue
      const by = Math.max(el.scrollWidth - el.clientWidth, el.scrollHeight - el.clientHeight)
      if (by > 1) {
        el.setAttribute(attribute, String(by))
        count += 1
      }
    }
    return count
  }, mark)
}

/** What overflows its box with 1.4.12's spacing applied that didn't before. */
export async function textSpacingFindings(page: Page): Promise<string[]> {
  await installDescribe(page)
  // A web font that arrives between the two measurements changes every width, so wait for them.
  await page.evaluate(() => document.fonts.ready)
  const BEFORE = 'data-a11y-over-before'
  const AFTER = 'data-a11y-over-after'
  await overflowing(page, BEFORE)
  const sheet = await page.evaluateHandle((css) => {
    const added = new CSSStyleSheet()
    added.replaceSync(css)
    document.adoptedStyleSheets = [...document.adoptedStyleSheets, added]
    return added
  }, TEXT_SPACING_CSS)
  await settle(page)
  await overflowing(page, AFTER)
  // Read again a moment later and keep only what overflowed both times: a box caught mid-layout
  // (`text-wrap: pretty` and a flex row can settle a few frames late) isn't a finding.
  await page.waitForTimeout(150)
  await settle(page)
  await page.evaluate((attribute) => {
    for (const el of document.querySelectorAll<HTMLElement>(`[${attribute}]`)) {
      const by = Math.max(el.scrollWidth - el.clientWidth, el.scrollHeight - el.clientHeight)
      if (by <= 1) el.removeAttribute(attribute)
    }
  }, AFTER)
  const found = await page.evaluate(
    ([before, after]) => {
      const describe = (window as unknown as { __a11yDescribe: (el: Element) => string })
        .__a11yDescribe
      const out: string[] = []
      const root = document.documentElement
      if (root.scrollWidth > root.clientWidth) out.push('the page scrolls sideways')
      for (const el of document.querySelectorAll(`[${after}]`)) {
        if (el.hasAttribute(before)) continue
        // How the words are lost: cut short with an ellipsis (the design's truncation, now
        // earlier), clipped by the box, or spilling out of it, where they can overlap a neighbor.
        const style = getComputedStyle(el)
        const how =
          style.textOverflow === 'ellipsis'
            ? 'is cut short with an ellipsis'
            : /hidden|clip/.test(style.overflowX + style.overflowY)
              ? 'is clipped by its box'
              : 'spills out of its box'
        // Where it is: the nearest part of the page with a name of its own (a `data-slot`).
        const own = el.getAttribute('data-slot')
        const part = el.closest('[data-slot]')?.getAttribute('data-slot')
        const where = part && part !== own ? ` in [${part}]` : ''
        out.push(`${describe(el)}${where} ${how} (${el.getAttribute(after)} px)`)
      }
      for (const el of document.querySelectorAll(`[${before}], [${after}]`)) {
        el.removeAttribute(before)
        el.removeAttribute(after)
      }
      return out
    },
    [BEFORE, AFTER] as const,
  )
  await sheet.evaluate((added) => {
    document.adoptedStyleSheets = document.adoptedStyleSheets.filter((s) => s !== added)
  })
  await settle(page)
  return found
}

export async function expectTextSpacing(page: Page) {
  expect(await textSpacingFindings(page), "no text is lost with 1.4.12's spacing").toEqual([])
}

// ---------------------------------------------------------------------------------------------
// Reduced motion: with `prefers-reduced-motion: reduce`, nothing animates. The caller turns the
// setting on (`page.emulateMedia({ reducedMotion: 'reduce' })`) before the state's interactions.

export async function motionFindings(page: Page): Promise<string[]> {
  await installDescribe(page)
  return page.evaluate(() => {
    const describe = (window as unknown as { __a11yDescribe: (el: Element) => string })
      .__a11yDescribe
    return document
      .getAnimations()
      .filter((a) => a.playState === 'running')
      .map((a) => {
        const name =
          a instanceof CSSAnimation
            ? `animation ${a.animationName}`
            : a instanceof CSSTransition
              ? `transition of ${a.transitionProperty}`
              : 'script animation'
        const target = (a.effect as KeyframeEffect | null)?.target
        return `${name} on ${target ? describe(target) : 'the page'}`
      })
  })
}

export async function expectNoMotion(page: Page) {
  expect(await motionFindings(page), 'nothing moves with reduced motion on').toEqual([])
}

// ---------------------------------------------------------------------------------------------
// Target size (2.5.8, AA): every pointer target is at least 24 by 24 CSS px, or a 24 px circle on
// its center touches no other target (and no other small target's circle). A link inside a
// sentence is exempt, and so is a disabled control. axe's own `target-size` rule runs in every
// scan too, but it reports a target another element partly covers as "incomplete", not as a
// violation, so a target under the sticky composer slips past it.

const TARGETS = [
  'a[href]',
  'button',
  'input:not([type="hidden"])',
  'select',
  'textarea',
  'summary',
  '[role="button"]',
  '[role="link"]',
  '[role="checkbox"]',
  '[role="radio"]',
  '[role="switch"]',
  '[role="tab"]',
  '[role="menuitem"]',
  '[role="menuitemradio"]',
  '[role="option"]',
].join(', ')

export async function targetSizeFindings(page: Page): Promise<string[]> {
  await installDescribe(page)
  return page.evaluate((selector) => {
    const describe = (window as unknown as { __a11yDescribe: (el: Element) => string })
      .__a11yDescribe
    const MIN = 24
    // A target in a sentence (a link, or a citation marker drawn inline-flex) is exempt: its size
    // is set by the line of text it sits in.
    const inSentence = (el: Element) => {
      if (!getComputedStyle(el).display.startsWith('inline')) return false
      const parent = el.parentElement
      if (!parent) return false
      return [...parent.childNodes].some(
        (n) => n !== el && n.nodeType === Node.TEXT_NODE && (n.textContent ?? '').trim() !== '',
      )
    }
    const targets = [...document.querySelectorAll<HTMLElement>(selector)]
      .filter((el) => el.checkVisibility({ visibilityProperty: true, opacityProperty: true }))
      .filter((el) => !el.matches(':disabled, [aria-disabled="true"]'))
      // A target inside another (a button inside a link) counts as the outer one.
      .filter((el) => !el.parentElement?.closest(selector))
      .map((el) => ({ el, box: el.getBoundingClientRect() }))
      // Visually hidden controls (a native radio behind its label) aren't pointer targets.
      .filter(({ box }) => box.width > 1 && box.height > 1)
    const small = (box: DOMRect) => box.width < MIN - 0.5 || box.height < MIN - 0.5
    const center = (box: DOMRect) => ({ x: box.x + box.width / 2, y: box.y + box.height / 2 })
    const distanceToBox = (p: { x: number; y: number }, box: DOMRect) => {
      const dx = Math.max(box.left - p.x, 0, p.x - box.right)
      const dy = Math.max(box.top - p.y, 0, p.y - box.bottom)
      return Math.hypot(dx, dy)
    }
    const found: string[] = []
    for (const { el, box } of targets) {
      if (!small(box) || inSentence(el)) continue
      const c = center(box)
      const crowded = targets.some(({ el: other, box: otherBox }) => {
        if (other === el || el.contains(other) || other.contains(el)) return false
        // The circle may touch no other target, and two small targets' circles may not overlap.
        if (distanceToBox(c, otherBox) < MIN / 2) return true
        if (!small(otherBox)) return false
        const o = center(otherBox)
        return Math.hypot(o.x - c.x, o.y - c.y) < MIN
      })
      if (crowded) {
        found.push(
          `${describe(el)} is ${Math.round(box.width)} x ${Math.round(box.height)} px, too close to another target`,
        )
      }
    }
    return found
  }, TARGETS)
}

export async function expectTargetSizes(page: Page) {
  expect(await targetSizeFindings(page), 'every target is 24 px or has room around it').toEqual([])
}

// ---------------------------------------------------------------------------------------------
// Focus not obscured (2.4.11, AA): the focused element is not entirely hidden by something the
// page draws over it (the sticky header, the sticky composer, the tour's coach mark). Sampled on a
// 5 by 5 grid over the part of the element inside the window. An overlay with
// `pointer-events: none` isn't seen by `elementsFromPoint`; the app has none over its controls.

export type FocusView = { name: string; shown: number; inWindow: boolean }

/** How much of the focused element shows, from 0 to 1, and whether any of it is in the window. */
export async function focusView(page: Page): Promise<FocusView> {
  // A stop with no accessible name is named by its tag, slot, and classes, so it can be found.
  const name =
    (await focusedName(page)) ||
    (await page.evaluate(() => {
      const el = document.activeElement
      if (!el || el === document.body) return '(body)'
      const slot = el.getAttribute('data-slot')
      return `(unnamed ${el.tagName.toLowerCase()}${slot ? `[${slot}]` : ''} .${el.className.toString().slice(0, 80)})`
    }))
  const view = await page.evaluate(() => {
    const el = document.activeElement
    if (!el || el === document.body) return { shown: 0, inWindow: false }
    const box = el.getBoundingClientRect()
    const left = Math.max(box.left, 0)
    const right = Math.min(box.right, window.innerWidth)
    const top = Math.max(box.top, 0)
    const bottom = Math.min(box.bottom, window.innerHeight)
    if (right <= left || bottom <= top) return { shown: 0, inWindow: false }
    let hits = 0
    const N = 5
    for (let i = 0; i < N; i += 1) {
      for (let j = 0; j < N; j += 1) {
        const x = left + ((i + 0.5) * (right - left)) / N
        const y = top + ((j + 0.5) * (bottom - top)) / N
        const topmost = document.elementFromPoint(x, y)
        if (topmost && (topmost === el || el.contains(topmost) || topmost.contains(el))) hits += 1
      }
    }
    // The share of the WHOLE element that shows: a part scrolled out of the window is hidden too.
    const inside = ((right - left) * (bottom - top)) / Math.max(box.width * box.height, 1)
    return { shown: (hits / (N * N)) * inside, inWindow: true }
  })
  return { name, ...view }
}

/** Asserts the focused element isn't entirely hidden; returns how much of it shows. */
export async function expectFocusNotObscured(page: Page): Promise<FocusView> {
  const view = await focusView(page)
  expect(view.shown, `"${view.name}" is focused and not entirely hidden`).toBeGreaterThan(0)
  return view
}

/**
 * Whether the focused element draws a ring: a 2 px outline, or a shadow in the focus ring's color
 * (at any opacity: a text box's halo is the ring's color at 18%), on it or on a close ancestor that
 * draws it for it (a console row draws its ring around the button inside it, with
 * `:has(:focus-visible)`; a text box's wrapper, with `:focus-within`). Any other shadow doesn't
 * count: cards and buttons have one at rest. Waits for a transition on them to finish first, since
 * a ring that fades in reads as its starting value.
 */
export const focusRingShows = (page: Page) =>
  page.evaluate(async () => {
    const el = document.activeElement
    if (!el || el === document.body) return false
    const chain: Element[] = [el]
    for (let p = el.parentElement, i = 0; p && i < 3; p = p.parentElement, i += 1) chain.push(p)
    await Promise.all(
      document
        .getAnimations()
        .filter(
          (a) =>
            a instanceof CSSTransition &&
            chain.includes((a.effect as KeyframeEffect | null)?.target as Element),
        )
        .map((a) => a.finished.catch(() => undefined)),
    )
    // The ring's color as red, green, and blue from 0 to 255. With no ring token (a transparent
    // probe), no shadow counts, or every black resting shadow would pass.
    const probe = document.createElement('i')
    probe.style.color = 'var(--color-focus-ring, transparent)'
    document.body.append(probe)
    const ring = (/rgba?\(([^)]+)\)/.exec(getComputedStyle(probe).color)?.[1] ?? '')
      .split(',')
      .map(Number)
    probe.remove()
    // Each color in a computed shadow, as `rgb(…)`, `rgba(…)`, or `color(srgb r g b / a)`.
    const shadowColors = (shadow: string) => {
      const colors: { rgb: number[]; alpha: number }[] = []
      for (const m of shadow.matchAll(/rgba?\(([^)]+)\)/g)) {
        const [r, g, b, a] = m[1]!.split(',').map(Number)
        colors.push({ rgb: [r!, g!, b!], alpha: a ?? 1 })
      }
      for (const m of shadow.matchAll(/color\(srgb ([^)]+)\)/g)) {
        const [rgb, a] = m[1]!.split('/')
        colors.push({
          rgb: rgb!
            .trim()
            .split(/\s+/)
            .map((v) => Number(v) * 255),
          alpha: a === undefined ? 1 : Number(a),
        })
      }
      return colors
    }
    const ringShadow = (node: Element) =>
      shadowColors(getComputedStyle(node).boxShadow).some(
        ({ rgb, alpha }) =>
          ring.length === 3 && alpha > 0 && rgb.every((v, k) => Math.abs(v - ring[k]!) <= 2),
      )
    const outlined = (node: Element) => {
      const style = getComputedStyle(node)
      return style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) >= 2
    }
    return chain.some((node) => outlined(node) || ringShadow(node))
  })

/**
 * One step of a keyboard walk: press `key`, then check that focus is on `name`, that it shows a
 * ring (unless `ring: false`, for a heading focused programmatically, which draws none by design),
 * and that it's not entirely hidden. Returns how much of it shows, so a walk can note a partly
 * covered stop as a low finding.
 */
export async function step(
  page: Page,
  key: string,
  name: string | RegExp,
  { ring = true }: { ring?: boolean } = {},
): Promise<FocusView> {
  if (key) await page.keyboard.press(key)
  await expect
    .poll(() => focusedName(page), { message: `focus after ${key || 'the action'}` })
    [typeof name === 'string' ? 'toBe' : 'toMatch'](name as never)
  if (ring) expect(await focusRingShows(page), `"${String(name)}" shows its focus ring`).toBe(true)
  const view = await expectFocusNotObscured(page)
  notePartial(view)
  return view
}

/**
 * Notes a stop that shows only in part, as a low finding on the test (it passes 2.4.11, which asks
 * only that focus isn't entirely hidden). The walks' annotations list them in the report.
 */
function notePartial(view: FocusView) {
  if (view.shown > 0 && view.shown < 0.999) {
    test.info().annotations.push({
      type: 'partly covered',
      description: `"${view.name}" shows ${Math.round(view.shown * 100)}%`,
    })
  }
}

/** Checks the stop focus is on now: a ring, and not entirely hidden. Soft, so a walk lists all. */
async function checkStop(page: Page): Promise<FocusView> {
  const view = await focusView(page)
  expect.soft(await focusRingShows(page), `"${view.name}" shows its focus ring`).toBe(true)
  expect.soft(view.shown, `"${view.name}" is focused and not entirely hidden`).toBeGreaterThan(0)
  notePartial(view)
  return view
}

/**
 * Presses Tab until focus is on `name`, at most `limit` times, checking every stop on the way
 * (each one's ring, and that it isn't hidden). Fails if focus never gets there.
 */
export async function tabTo(
  page: Page,
  name: string | RegExp,
  { limit = 40, back = false }: { limit?: number; back?: boolean } = {},
): Promise<FocusView> {
  const matches = (n: string) => (typeof name === 'string' ? n === name : name.test(n))
  const passed: string[] = []
  for (let i = 0; i < limit; i += 1) {
    await page.keyboard.press(back ? 'Shift+Tab' : 'Tab')
    // Past the last control, focus leaves the page (to the browser's own controls) and the next
    // Tab comes back to the first. That's the wrap, not a stop of the page's.
    if (await page.evaluate(() => document.activeElement === document.body)) {
      passed.push('(the end of the page)')
      continue
    }
    const view = await checkStop(page)
    if (matches(view.name)) return view
    passed.push(view.name)
  }
  throw new Error(`Tab never reached ${String(name)}; it passed: ${passed.join(' | ')}`)
}
