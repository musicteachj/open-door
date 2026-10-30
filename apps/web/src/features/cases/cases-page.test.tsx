import { act, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import {
  AALIYAH_ROW,
  CHLOE,
  DANA_OWN_ROW,
  KEISHA,
  MEGAN_ROW,
  PRIYA_ROW,
} from '@/app/gallery/fixtures/cases'
import { installFakeApi } from '@/test/fake-api'
import { installFakeCases } from '@/test/fake-cases'
import { arrow } from '@/test/arrow-key'
import { renderApp } from '@/test/render-app'

// HR's queue at /cases (Task 37).

function open(
  options: Parameters<typeof installFakeCases>[0] = {},
  at = '/cases',
  persona: 'dana' | 'priya' | 'marcus' = 'dana',
) {
  installFakeApi(persona)
  const fake = installFakeCases(options)
  return { ...renderApp({ at }), fake }
}

const OPEN_PAGE = { items: [CHLOE, KEISHA, PRIYA_ROW, AALIYAH_ROW], nextCursor: null }
const queue = () => screen.findByRole('list', { name: 'Cases' })

describe('the queue: who can see it', () => {
  it.each(['priya', 'marcus'] as const)(
    'shows %s the Not found page, and asks for nothing',
    async (who) => {
      const { fake } = open({}, '/cases', who)
      expect(
        await screen.findByRole('heading', { level: 1, name: "We couldn't find that page." }),
      ).toBeVisible()
      expect(fake.calls.list).toEqual([])
    },
  )
})

describe('the queue', () => {
  it('lists the open cases by default, as the server ordered them', async () => {
    const { fake } = open({ queue: { '': OPEN_PAGE } })
    expect(await screen.findByRole('heading', { level: 1, name: 'Cases' })).toBeVisible()
    const table = await queue()
    expect(within(table).getAllByRole('link')).toHaveLength(4)
    expect(within(table).getByText('Chloe Foster')).toBeVisible()
    expect(fake.calls.list[0]).toEqual({ status: 'open', cursor: null })
  })

  it('takes the filter from the address, and changing it changes the address', async () => {
    const { user, fake, router } = open({ queue: { '': OPEN_PAGE } }, '/cases?status=closed')
    await queue()
    expect(fake.calls.list[0]!.status).toBe('closed')
    await user.click(screen.getByRole('radio', { name: 'New' }))
    expect(router.state.location.search).toBe('?status=new')
    await user.click(screen.getByRole('radio', { name: 'Open' }))
    expect(router.state.location.search).toBe('')
  })

  it('asks for every case with no filter for All', async () => {
    const { fake } = open({ queue: { '': OPEN_PAGE } }, '/cases?status=all')
    await queue()
    expect(fake.calls.list[0]).toEqual({ status: null, cursor: null })
  })

  it('treats an unknown filter as Open', async () => {
    const { fake } = open({ queue: { '': OPEN_PAGE } }, '/cases?status=bogus')
    await queue()
    expect(fake.calls.list[0]!.status).toBe('open')
  })

  it('says what is empty for each filter', async () => {
    open({}, '/cases?status=new')
    expect(await screen.findByText(/^No new cases/)).toBeVisible()
  })

  it('shows the crisis fact, and HR’s own case in the list', async () => {
    open({ queue: { '': { items: [MEGAN_ROW, DANA_OWN_ROW], nextCursor: null } } })
    const table = await queue()
    expect(within(table).getByText(/routed this message to crisis text/)).toBeVisible()
    // HR's own row is a link like the others: the detail opens its header and says why it stops.
    expect(within(table).getAllByRole('link')).toHaveLength(2)
  })

  it('pages with the cursor: more cases are added under the first page', async () => {
    const { user, fake } = open({
      queue: {
        '': { items: [CHLOE], nextCursor: 'c2' },
        c2: { items: [KEISHA], nextCursor: null },
      },
    })
    await queue()
    expect(screen.queryByText('Keisha Zhang')).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Show more cases' }))
    expect(await screen.findByText('Keisha Zhang')).toBeVisible()
    expect(screen.getByText('Chloe Foster')).toBeVisible()
    expect(fake.calls.list.at(-1)).toEqual({ status: 'open', cursor: 'c2' })
    expect(screen.queryByRole('button', { name: 'Show more cases' })).toBeNull()
  })
})

describe('the queue: paging', () => {
  it('makes one request when "Show more cases" is clicked twice before the page draws again', async () => {
    const { fake } = open({
      queue: {
        '': { items: [CHLOE], nextCursor: 'c2' },
        c2: { items: [KEISHA], nextCursor: null },
      },
    })
    await queue()
    const button = screen.getByRole('button', { name: 'Show more cases' })
    await act(async () => {
      button.click()
      button.click()
    })
    await screen.findByText('Keisha Zhang')
    expect(fake.calls.list.filter((call) => call.cursor === 'c2')).toHaveLength(1)
  })
})

describe('the queue filter', () => {
  it('stays mounted and keeps focus while a new filter loads, so arrow keys keep working', async () => {
    const { user } = open({ queue: { '': OPEN_PAGE } })
    await queue()
    const open1 = screen.getByRole('radio', { name: 'Open' })
    open1.focus()
    await arrow(user, 'ArrowRight')
    const next = screen.getByRole('radio', { name: 'New' })
    expect(next).toBeChecked()
    expect(next).toHaveFocus()
    await arrow(user, 'ArrowRight')
    expect(screen.getByRole('radio', { name: 'In review' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'In review' })).toHaveFocus()
  })
})

describe('the queue: the page head and paging errors', () => {
  it('has a lock before the heading and the confidentiality line under it', async () => {
    open({ queue: { '': OPEN_PAGE } })
    const title = await screen.findByRole('heading', { level: 1, name: 'Cases' })
    expect(title.parentElement!.querySelector('svg')).not.toBeNull()
    expect(screen.getByText(/Confidential\. Only the HR team can open these cases/)).toBeVisible()
  })

  it('says so when more cases could not be loaded, and keeps the button', async () => {
    const { user } = open({ queue: { '': { items: [CHLOE], nextCursor: 'bad' } } })
    await queue()
    await user.click(screen.getByRole('button', { name: 'Show more cases' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn’t be loaded/)
    expect(screen.getByRole('button', { name: 'Show more cases' })).toBeVisible()
  })

  it('keeps the extra pages when the first page is read again with the same data', async () => {
    const { user, queryClient, fake } = open({
      queue: {
        '': { items: [CHLOE], nextCursor: 'c2' },
        c2: { items: [KEISHA], nextCursor: null },
      },
    })
    await queue()
    await user.click(screen.getByRole('button', { name: 'Show more cases' }))
    await screen.findByText('Keisha Zhang')
    const reads = fake.calls.list.length
    await queryClient.invalidateQueries({ queryKey: ['/api/v1/cases'] })
    expect(fake.calls.list.length).toBe(reads + 1)
    expect(screen.getByText('Keisha Zhang')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Show more cases' })).toBeNull()
  })

  it('drops the extra pages when the first page is read again with changed data', async () => {
    const pages = {
      '': { items: [CHLOE], nextCursor: 'c2' },
      c2: { items: [KEISHA], nextCursor: null },
    }
    const { user, queryClient } = open({ queue: pages })
    await queue()
    await user.click(screen.getByRole('button', { name: 'Show more cases' }))
    await screen.findByText('Keisha Zhang')
    pages[''] = { items: [CHLOE, PRIYA_ROW], nextCursor: 'c2' }
    await queryClient.invalidateQueries({ queryKey: ['/api/v1/cases'] })
    await vi.waitFor(() => expect(screen.queryByText('Keisha Zhang')).toBeNull())
    expect(screen.getByRole('button', { name: 'Show more cases' })).toBeVisible()
  })
})
