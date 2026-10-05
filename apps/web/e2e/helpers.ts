import { expect, type Page } from '@playwright/test'

/** Starts a sandbox from the landing page and waits for /ask. */
export async function startAs(page: Page, name: 'Priya' | 'Marcus') {
  await page.goto('/')
  await page.getByRole('button', { name: `Start as ${name}` }).click()
  await expect(page).toHaveURL('/ask')
}
