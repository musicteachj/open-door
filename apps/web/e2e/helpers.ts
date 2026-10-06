import { expect, type Page } from '@playwright/test'

/** Starts a sandbox from the landing page and waits for /ask. */
export async function startAs(page: Page, name: 'Priya' | 'Marcus') {
  await page.goto('/')
  await page.getByRole('button', { name: `Start as ${name}` }).click()
  await expect(page).toHaveURL('/ask')
}

/** A theme color as the browser computes it, for comparing with computed fills and borders. */
export const themeColor = (page: Page, token: string) =>
  page.evaluate((name) => {
    const probe = document.createElement('div')
    probe.style.color = `var(--color-${name})`
    document.body.append(probe)
    const color = getComputedStyle(probe).color
    probe.remove()
    return color
  }, token)
