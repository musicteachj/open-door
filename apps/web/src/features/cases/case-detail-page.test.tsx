import { act, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  AALIYAH_CASE,
  DANA_OWN_CASE,
  MEGAN_CASE,
  PRIYA_CASE,
  timelineEntry,
  type DemoCase,
} from '@/app/gallery/fixtures/cases'
import type { CaseSummaryOut } from '@/api/generated'
import { installFakeApi } from '@/test/fake-api'
import { detailOf, installFakeCases } from '@/test/fake-cases'
import { problemResponse } from '@/test/fake-assistant'
import { meFor } from '@/test/fixtures'
import { renderApp } from '@/test/render-app'
import { readTiming } from './use-case-reads'

const announceMock = vi.hoisted(() => vi.fn<(text: string, politeness?: string) => void>())
vi.mock('@/lib/announce', () => ({ announce: announceMock, resetAnnouncer: () => {} }))

// A case's detail at /cases/:caseId (Task 37). The summary and the words are audited reads: these
// tests count them, and look into the query cache for them.

const DANA_ID = meFor('dana').id
const WRITTEN: CaseSummaryOut = {
  status: 'written',
  text: 'The person says their manager keeps making comments about their age.',
  model: 'claude-opus-5-5',
  createdAt: '2026-10-26T16:41:00Z',
}

/** The case's timeline with every read and change by Dana, the signed-in HR person. */
const byDana = (c: DemoCase): DemoCase => ({
  ...c,
  entries: c.entries.map((e) => (e.actorPersonId === null ? e : { ...e, actorPersonId: DANA_ID })),
})

function open(
  c: DemoCase,
  options: {
    persona?: 'dana' | 'priya' | 'marcus'
    summary?: CaseSummaryOut | { problem: number }
    words?: string | { problem: number }
    summaryState?: Parameters<typeof detailOf>[1]
    strict?: boolean
  } = {},
) {
  const { persona = 'dana', summary = WRITTEN, words = c.words, summaryState, strict } = options
  installFakeApi(persona)
  const fake = installFakeCases({
    details: { [c.id]: detailOf(c, summaryState) },
    summaries: { [c.id]: summary },
    words: { [c.id]: words },
  })
  return { ...renderApp({ at: `/cases/${c.id}`, strict }), fake, id: c.id }
}

const heading = (name: string | RegExp) => screen.findByRole('heading', { level: 1, name })
const showButton = (first = 'Priya') =>
  screen.findByRole('button', { name: `Show ${first}’s words` })
const startReview = () => screen.getByRole('button', { name: 'Start review' })
const closeCase = () => screen.getByRole('button', { name: 'Close case' })
const cacheKeys = (client: ReturnType<typeof renderApp>['queryClient']) =>
  client
    .getQueryCache()
    .getAll()
    .map((q) => JSON.stringify(q.queryKey))

afterEach(() => {
  readTiming.pollMs = 4000
  readTiming.tickMs = 15_000
})

describe('the detail: who can see it', () => {
  it.each(['priya', 'marcus'] as const)(
    'shows %s the Not found page, and reads nothing',
    async (who) => {
      const { fake } = open(PRIYA_CASE, { persona: who })
      expect(
        await screen.findByRole('heading', { level: 1, name: "We couldn't find that page." }),
      ).toBeVisible()
      expect(fake.calls.detail).toEqual([])
      expect(fake.calls.summary).toEqual([])
      expect(fake.calls.text).toEqual([])
    },
  )

  it('shows Not found for a case that does not exist', async () => {
    installFakeApi('dana')
    installFakeCases()
    renderApp({ at: '/cases/nope' })
    expect(
      await screen.findByRole('heading', { level: 1, name: "We couldn't find that page." }),
    ).toBeVisible()
  })
})

describe('the detail: the page', () => {
  it('shows the header, the person, the summary, the hidden words, and the timeline', async () => {
    const { fake } = open(PRIYA_CASE)
    expect(await heading('Harassment or discrimination')).toBeVisible()
    expect(screen.getByText('Priya Raman')).toBeVisible()
    expect(await screen.findByText(WRITTEN.text!)).toBeVisible()
    expect(screen.getByText(/words are hidden/)).toBeVisible()
    expect(screen.getByRole('heading', { level: 2, name: 'Timeline' })).toBeVisible()
    // One view: one summary read, and no words read.
    expect(fake.calls.summary).toEqual([PRIYA_CASE.id])
    expect(fake.calls.text).toEqual([])
  })

  it('reads the summary once for a view, even in StrictMode', async () => {
    const { fake } = open(PRIYA_CASE, { strict: true })
    await screen.findByText(WRITTEN.text!)
    expect(fake.calls.summary).toHaveLength(1)
  })

  it('reads the summary once per view when the metadata is already cached, even in StrictMode', async () => {
    // With the metadata cached the effect runs on the page's first render, which StrictMode runs
    // twice, so this is the case the ref guard is for.
    const { fake, router, id } = open(PRIYA_CASE, { strict: true })
    await screen.findByText(WRITTEN.text!)
    await act(() => router.navigate('/cases'))
    await screen.findByRole('heading', { level: 1, name: 'Cases' })
    await act(() => router.navigate(`/cases/${id}`))
    await screen.findByText(WRITTEN.text!)
    expect(fake.calls.summary).toHaveLength(2)
  })

  it('never puts the summary or the words in the query cache', async () => {
    const { user, queryClient } = open(PRIYA_CASE)
    await screen.findByText(WRITTEN.text!)
    await user.click(await showButton())
    await screen.findByText(PRIYA_CASE.words)
    const keys = cacheKeys(queryClient)
    // (The time-off summary route is a different thing, so match the case routes.)
    expect(keys.some((key) => /\/api\/v1\/cases\/[^"]+\/(summary|text)/.test(key))).toBe(false)
    // The metadata is fine there.
    expect(keys.some((key) => key.includes(`/api/v1/cases/${PRIYA_CASE.id}`))).toBe(true)
  })

  it('makes no audited call when the window gets focus again or the network returns', async () => {
    const { user, fake } = open(PRIYA_CASE)
    await screen.findByText(WRITTEN.text!)
    await user.click(await showButton())
    await screen.findByText(PRIYA_CASE.words)
    act(() => {
      window.dispatchEvent(new Event('focus'))
      window.dispatchEvent(new Event('online'))
      document.dispatchEvent(new Event('visibilitychange'))
    })
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(fake.calls.summary).toHaveLength(1)
    expect(fake.calls.text).toHaveLength(1)
  })

  it('shows HR’s own case as a header and a notice, and makes no audited read', async () => {
    const { fake } = open(DANA_OWN_CASE)
    expect(await heading('Pay concern')).toBeVisible()
    expect(await screen.findByText(/You opened this case/)).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'AI summary' })).toBeNull()
    expect(screen.queryByRole('button', { name: /Show .* words/ })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Close case' })).toBeNull()
    expect(fake.calls.summary).toEqual([])
    expect(fake.calls.text).toEqual([])
  })

  it('shows a crisis case with no summary read', async () => {
    const { fake } = open(MEGAN_CASE)
    expect(await screen.findByText(/No AI summary for this case/)).toBeVisible()
    expect(fake.calls.summary).toEqual([])
  })
})

describe('the words', () => {
  it('opens on the press only, adds one timeline row, and unlocks the actions', async () => {
    const { user, fake } = open(PRIYA_CASE)
    await screen.findByText(WRITTEN.text!)
    expect(closeCase()).toHaveAttribute('aria-disabled', 'true')
    const before = screen.getAllByRole('listitem').length
    await user.click(await showButton())
    expect(await screen.findByText(PRIYA_CASE.words)).toBeVisible()
    expect(fake.calls.text).toEqual([PRIYA_CASE.id])
    await waitFor(() => expect(screen.getAllByRole('listitem').length).toBe(before + 1))
    expect(closeCase()).not.toHaveAttribute('aria-disabled')
    expect(startReview()).not.toHaveAttribute('aria-disabled')
  })

  it('drops the words on Hide, and each new reveal is one more read', async () => {
    const { user, fake } = open(PRIYA_CASE)
    await user.click(await showButton())
    await screen.findByText(PRIYA_CASE.words)
    await user.click(screen.getByRole('button', { name: 'Hide Priya’s words' }))
    expect(screen.queryByText(PRIYA_CASE.words)).toBeNull()
    expect(fake.calls.text).toHaveLength(1)
    await user.click(screen.getByRole('button', { name: 'Show Priya’s words' }))
    await screen.findByText(PRIYA_CASE.words)
    expect(fake.calls.text).toHaveLength(2)
  })

  it('says the words could not be opened, and tries again on the next press', async () => {
    const { user, fake } = open(PRIYA_CASE, { words: { problem: 500 } })
    await user.click(await showButton())
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn’t be opened/)
    expect(closeCase()).toHaveAttribute('aria-disabled', 'true')
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(fake.calls.text).toHaveLength(2))
  })

  it('starts with the actions unlocked when this person read the words on an earlier view', async () => {
    open(byDana(AALIYAH_CASE))
    await screen.findByRole('heading', { level: 1, name: 'Workplace safety' })
    expect(closeCase()).not.toHaveAttribute('aria-disabled')
  })

  it('does not count another person’s read as this person’s', async () => {
    open(AALIYAH_CASE)
    await screen.findByRole('heading', { level: 1, name: 'Workplace safety' })
    expect(closeCase()).toHaveAttribute('aria-disabled', 'true')
  })
})

describe('changing the status', () => {
  async function readThen(c: DemoCase) {
    const view = open(c)
    await screen.findByText(WRITTEN.text!)
    await view.user.click(await showButton(c.name.split(' ')[0]))
    await screen.findByText(c.words)
    return view
  }

  it('Start review confirms, changes the status once, and moves focus to Close case', async () => {
    const { user, fake } = await readThen(PRIYA_CASE)
    await user.click(startReview())
    const dialog = await screen.findByRole('alertdialog')
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toHaveFocus()
    await user.click(within(dialog).getByRole('button', { name: 'Start review' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(fake.calls.status).toEqual([{ id: PRIYA_CASE.id, to: 'in_review' }])
    await waitFor(() => expect(closeCase()).toHaveFocus())
    // The page shows what the server now says.
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Start review' })).toBeNull())
  })

  it('Close case moves focus to the heading and hides the words', async () => {
    const { user, fake } = await readThen(PRIYA_CASE)
    await user.click(closeCase())
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: 'Close case' }))
    await waitFor(() => expect(fake.calls.status).toEqual([{ id: PRIYA_CASE.id, to: 'closed' }]))
    const title = await heading('Harassment or discrimination')
    await waitFor(() => expect(title).toHaveFocus())
    expect(screen.queryByText(PRIYA_CASE.words)).toBeNull()
    expect(await screen.findByText('This case is closed.')).toBeVisible()
  })

  it('Cancel returns focus to the button that opened the dialog', async () => {
    const { user, fake } = await readThen(PRIYA_CASE)
    await user.click(startReview())
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Cancel' }),
    )
    await waitFor(() => expect(startReview()).toHaveFocus())
    expect(fake.calls.status).toEqual([])
  })

  it('locks the actions again when the server says the words were not read', async () => {
    const { user, fake } = await readThen(PRIYA_CASE)
    fake.onStatus(() => problemResponse(409, 'words-not-read', 'Read the words first.'))
    await user.click(closeCase())
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Close case' }),
    )
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    await waitFor(() => expect(closeCase()).toHaveAttribute('aria-disabled', 'true'))
    expect(screen.getByText(/Read Priya’s words before changing the status/)).toBeVisible()
    await waitFor(() => expect(closeCase()).toHaveFocus())
  })

  it('keeps the case as it was and says so when the change fails', async () => {
    const { user, fake } = await readThen(PRIYA_CASE)
    fake.onStatus(() => problemResponse(500, 'about:blank', 'Broke.'))
    await user.click(closeCase())
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Close case' }),
    )
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(screen.getByRole('button', { name: 'Close case' })).toBeVisible()
    expect(screen.getByText(PRIYA_CASE.words)).toBeVisible()
  })
})

describe('the summary', () => {
  it('shows it as being written, polls the metadata, and reads it once when it exists', async () => {
    readTiming.pollMs = 20
    const recent = new Date(Date.now() - 10_000).toISOString()
    const c: DemoCase = {
      ...PRIYA_CASE,
      sentAt: recent,
      entries: [timelineEntry('opened', recent)],
    }
    const { fake } = open(c, { summaryState: { summary: { status: 'none' } } })
    expect(await screen.findByText('Writing the summary…')).toBeVisible()
    await waitFor(() => expect(fake.calls.detail.length).toBeGreaterThan(2))
    expect(fake.calls.summary).toEqual([])
    fake.details[c.id] = detailOf(c, { summary: { status: 'written', createdAt: recent } })
    expect(await screen.findByText(WRITTEN.text!)).toBeVisible()
    expect(fake.calls.summary).toEqual([c.id])
    const polled = fake.calls.detail.length
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(fake.calls.detail.length).toBe(polled)
  })

  it('offers Try again once the summary is 2.5 minutes late, on a timer', async () => {
    readTiming.tickMs = 30
    const late = new Date(Date.now() - 150_000 + 400).toISOString()
    const c: DemoCase = { ...PRIYA_CASE, sentAt: late, entries: [timelineEntry('opened', late)] }
    open(c, { summaryState: { summary: { status: 'none' } } })
    expect(await screen.findByText('Writing the summary…')).toBeVisible()
    expect(await screen.findByRole('button', { name: 'Try again' })).toBeVisible()
  })

  it('writes a new summary on Try again, and stays pending when the server refuses', async () => {
    const old = '2026-10-20T10:00:00Z'
    const c: DemoCase = { ...PRIYA_CASE, sentAt: old, entries: [timelineEntry('opened', old)] }
    const { user, fake } = open(c, {
      summaryState: { summary: { status: 'failed', reason: 'model-error', createdAt: old } },
    })
    fake.onRewrite(() => problemResponse(409, 'summary-retry-refused', 'Too soon.'))
    await user.click(await screen.findByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Writing the summary…')).toBeVisible()
    expect(fake.calls.rewrites).toEqual([c.id])
    expect(fake.calls.summary).toEqual([])
  })

  it('shows the new summary after Try again once the metadata says it is written', async () => {
    readTiming.pollMs = 20
    const old = '2026-10-20T10:00:00Z'
    const c: DemoCase = { ...PRIYA_CASE, sentAt: old, entries: [timelineEntry('opened', old)] }
    const { user, fake } = open(c, {
      summaryState: { summary: { status: 'failed', reason: 'model-error', createdAt: old } },
    })
    await user.click(await screen.findByRole('button', { name: 'Try again' }))
    await screen.findByText('Writing the summary…')
    fake.details[c.id] = detailOf(c, {
      summary: { status: 'written', createdAt: '2026-10-29T10:00:00Z' },
    })
    expect(await screen.findByText(WRITTEN.text!)).toBeVisible()
    expect(fake.calls.summary).toEqual([c.id])
  })

  it('reads the summary again, not a new one, when the first read failed', async () => {
    const { user, fake } = open(PRIYA_CASE, { summary: { problem: 500 } })
    const retry = await screen.findByRole('button', { name: 'Try again' })
    expect(fake.calls.summary.length).toBeGreaterThanOrEqual(1)
    const before = fake.calls.summary.length
    await user.click(retry)
    await waitFor(() => expect(fake.calls.summary.length).toBe(before + 1))
    expect(fake.calls.rewrites).toEqual([])
  })
})

describe('reads that overlap or are dropped', () => {
  it('keeps the words hidden when the case is closed while they were still loading', async () => {
    const c = byDana(AALIYAH_CASE)
    const { user, fake } = open(c)
    await screen.findByText(WRITTEN.text!)
    const release = fake.hold('text')
    await user.click(await showButton('Aaliyah'))
    await waitFor(() => expect(fake.calls.text).toHaveLength(1))
    await user.click(closeCase())
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Close case' }),
    )
    await screen.findByText('This case is closed.')
    release()
    await new Promise((resolve) => setTimeout(resolve, 80))
    expect(screen.queryByText(c.words)).toBeNull()
  })

  it('keeps the newer summary when an older read finishes later', async () => {
    const { fake, queryClient, id } = open(PRIYA_CASE)
    await screen.findByText(WRITTEN.text!)
    // The first read is already done; hold the next one, then make a newer one that finishes first.
    const release = fake.hold('summary')
    fake.details[id] = detailOf(PRIYA_CASE, {
      summary: { status: 'written', createdAt: '2026-10-27T10:00:00Z' },
    })
    await queryClient.invalidateQueries({ queryKey: [`/api/v1/cases/${id}`] })
    await waitFor(() => expect(fake.calls.summary).toHaveLength(2))
    fake.summaries[id] = {
      ...WRITTEN,
      text: 'The newer summary.',
      createdAt: '2026-10-27T10:00:00Z',
    }
    fake.details[id] = detailOf(PRIYA_CASE, {
      summary: { status: 'written', createdAt: '2026-10-28T10:00:00Z' },
    })
    await queryClient.invalidateQueries({ queryKey: [`/api/v1/cases/${id}`] })
    expect(await screen.findByText('The newer summary.')).toBeVisible()
    release()
    await new Promise((resolve) => setTimeout(resolve, 80))
    expect(screen.getByText('The newer summary.')).toBeVisible()
    expect(screen.queryByText(WRITTEN.text!)).toBeNull()
  })

  it('sends one new-summary request for two quick presses of Try again', async () => {
    const old = '2026-10-20T10:00:00Z'
    const c: DemoCase = { ...PRIYA_CASE, sentAt: old, entries: [timelineEntry('opened', old)] }
    const { fake } = open(c, {
      summaryState: { summary: { status: 'failed', reason: 'model-error', createdAt: old } },
    })
    const button = await screen.findByRole('button', { name: 'Try again' })
    act(() => {
      button.click()
      button.click()
    })
    await screen.findByText('Writing the summary…')
    expect(fake.calls.rewrites).toEqual([c.id])
  })

  it('stops the clock once the summary has failed', async () => {
    readTiming.tickMs = 37
    const started: unknown[] = []
    const cleared = new Set<unknown>()
    const realSet = globalThis.setInterval
    const realClear = globalThis.clearInterval
    globalThis.setInterval = ((fn: () => void, ms?: number) => {
      const id = realSet(fn, ms)
      if (ms === 37) started.push(id)
      return id
    }) as typeof setInterval
    globalThis.clearInterval = ((id: Parameters<typeof clearInterval>[0]) => {
      cleared.add(id)
      return realClear(id)
    }) as typeof clearInterval
    try {
      const late = new Date(Date.now() - 150_000 + 300).toISOString()
      const c: DemoCase = { ...PRIYA_CASE, sentAt: late, entries: [timelineEntry('opened', late)] }
      open(c, { summaryState: { summary: { status: 'none' } } })
      await screen.findByRole('button', { name: 'Try again' })
      expect(started.length).toBeGreaterThan(0)
      await waitFor(() => expect(started.every((id) => cleared.has(id))).toBe(true))
    } finally {
      globalThis.setInterval = realSet
      globalThis.clearInterval = realClear
    }
  })
})

describe('the timeline after the summary is read', () => {
  it('gains the "read the AI summary" row, without announcing it', async () => {
    const { fake, id } = open(PRIYA_CASE)
    // What the server's timeline gains when HR reads the summary.
    const base = fake.details[id]!
    const viewed = timelineEntry('viewed', '2026-10-26T17:30:00Z', { actorPersonId: DANA_ID })
    fake.summaries[id] = WRITTEN
    const original = fake.details[id]
    const calls = fake.calls.detail
    // The metadata the page reads after the summary read includes the new row.
    let summaryRead = false
    const poll = setInterval(() => {
      if (fake.calls.summary.length > 0 && !summaryRead) {
        summaryRead = true
        fake.details[id] = { ...base, timeline: [...base.timeline!, viewed] }
      }
    }, 1)
    try {
      await screen.findByText(WRITTEN.text!)
      expect(await screen.findByText(/read the AI summary/)).toBeVisible()
    } finally {
      clearInterval(poll)
    }
    expect(original).toBeDefined()
    expect(calls.length).toBeGreaterThanOrEqual(2)
    expect(announceMock).not.toHaveBeenCalledWith(expect.stringContaining('read the AI summary'))
  })
})
