import { screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { BudgetOut, PersonaKey, TurnOut } from '@/api/generated'
import { DANA } from '@/test/assistant-fixtures'
import { installFakeApi } from '@/test/fake-api'
import { conversationOut, installAssistantApi, turnOut } from '@/test/fake-assistant'
import { renderApp } from '@/test/render-app'

// "Write to HR" is for a person, never for HR (who has no My cases page): after the contacts of
// the "can't answer right now" panel and of a not-found answer, and in the budget banner.

vi.mock('@/lib/announce', () => ({ announce: vi.fn<() => void>(), resetAnnouncer: () => {} }))

const notFound = turnOut({
  id: 't-1',
  question: 'Tuition?',
  answerText: 'I couldn’t find that.',
  notFound: true,
})
const unavailable = turnOut({
  id: 't-2',
  question: 'How many sick days do I get?',
  status: 'guard_unavailable',
  answerText: '',
  guard: null,
  escalation: {
    kind: 'unavailable',
    message: 'We can’t answer right now.',
    hrContact: [DANA],
    offerCase: false,
  },
})
const sandboxBudget: BudgetOut = {
  sandboxReached: true,
  dailyReached: false,
  sandboxRemainingCents: 0,
  banner: { kind: 'sandbox', message: 'This sandbox has used its assistant budget.' },
}
const dailyBudget: BudgetOut = {
  sandboxReached: false,
  dailyReached: true,
  sandboxRemainingCents: 100,
  banner: { kind: 'daily', message: 'Today’s demo budget is reached.' },
}

function open(persona: PersonaKey, turns: TurnOut[], budget?: BudgetOut) {
  installFakeApi(persona)
  installAssistantApi({ conversation: conversationOut({ turns, hrContacts: [DANA], budget }) })
  return renderApp({ at: '/ask' })
}

const write = () => screen.queryAllByRole('link', { name: 'Write to HR' })

describe('Write to HR for a person', () => {
  it('follows the contacts of the unavailable panel', async () => {
    open('priya', [unavailable])
    const panel = await screen.findByRole('region', { name: "Can't answer right now" })
    const link = within(panel).getByRole('link', { name: 'Write to HR' })
    expect(link).toHaveAttribute('href', '/my-cases')
    const contacts = within(panel).getByText('HR team')
    expect(contacts.compareDocumentPosition(link) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('follows the contacts of a not-found answer', async () => {
    open('priya', [notFound])
    await screen.findByText('HR contacts')
    expect(write()).toHaveLength(1)
    expect(write()[0]).toHaveAttribute('href', '/my-cases')
  })

  it('is in the sandbox budget banner, after its text', async () => {
    open('priya', [notFound], sandboxBudget)
    const text = await screen.findByText(/This sandbox has used its assistant budget\./)
    const banner = text.closest('[data-slot="banner"]')!
    expect(
      within(banner as HTMLElement).getByRole('link', { name: 'Write to HR' }),
    ).toHaveAttribute('href', '/my-cases')
  })

  it('is in the daily banner, and on the home with no conversation', async () => {
    open('priya', [], dailyBudget)
    const text = await screen.findByText(/Today’s demo budget is reached\./)
    const banner = text.closest('[data-slot="banner"]')!
    expect(within(banner as HTMLElement).getByRole('link', { name: 'Write to HR' })).toBeVisible()
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
  })
})

describe('Write to HR is never offered to HR', () => {
  it('leaves it off the unavailable panel and a not-found answer', async () => {
    open('dana', [notFound, unavailable])
    await screen.findByRole('region', { name: "Can't answer right now" })
    expect(screen.getAllByText('HR contacts')).toHaveLength(2)
    expect(write()).toHaveLength(0)
  })

  it('leaves it off both banners', async () => {
    open('dana', [unavailable], sandboxBudget)
    await screen.findByText(/This sandbox has used its assistant budget\./)
    expect(write()).toHaveLength(0)
  })

  it('leaves it off the banner on the home', async () => {
    open('dana', [], dailyBudget)
    await screen.findByText(/Today’s demo budget is reached\./)
    expect(write()).toHaveLength(0)
  })
})

describe('a model-written link to a case page, by who reads it', () => {
  const written = turnOut({
    id: 't-9',
    question: 'Where do I write?',
    answerText: 'Use [Write to HR](/my-cases) or see [the queue](/cases/abc).',
  })

  it('is a link to My cases for a person, and plain text for the queue', async () => {
    open('priya', [written])
    expect(await screen.findByRole('link', { name: 'Write to HR' })).toHaveAttribute(
      'href',
      '/my-cases',
    )
    expect(screen.queryByRole('link', { name: 'the queue' })).toBeNull()
  })

  it('is a link to the queue for HR, and plain text for My cases', async () => {
    open('dana', [written])
    expect(await screen.findByRole('link', { name: 'the queue' })).toHaveAttribute(
      'href',
      '/cases/abc',
    )
    expect(screen.queryByRole('link', { name: 'Write to HR' })).toBeNull()
  })
})
