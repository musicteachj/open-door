import { QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { useEffect, useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ProposalOut } from '@/api/generated'
import { getGetCurrentConversationQueryKey } from '@/api/generated'
import { resetIdentity } from '@/lib/identity'
import { createQueryClient } from '@/lib/query-client'
import { installFakeApi } from '@/test/fake-api'
import { proposalOut } from '@/test/fake-assistant'
import { ProposalCards } from './proposal-cards'
import { yearNow } from './proposal-time'

// One timer per pending card, at the moment it expires, and the year the card is read in.

const NOW = new Date('2026-10-20T22:27:00Z')

function setup(expiresInMs: number, status: 'pending' | 'executed' = 'pending') {
  const queryClient = createQueryClient({ onUnauthorized: vi.fn<() => void>(), retryDelayMs: 0 })
  const invalidate = vi.spyOn(queryClient, 'invalidateQueries').mockResolvedValue()
  const proposal = proposalOut({
    status,
    expiresAt: new Date(NOW.getTime() + expiresInMs).toISOString(),
  })
  const tree = (shown: typeof proposal) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ProposalCards proposals={[shown]} question="Can I take Friday off?" />
      </MemoryRouter>
    </QueryClientProvider>
  )
  const view = render(tree(proposal))
  const rerender = (next: 'expired') => view.rerender(tree({ ...proposal, status: next }))
  return { invalidate, view, queryClient, rerender }
}

const conversationReads = (invalidate: { mock: { calls: unknown[][] } }) =>
  invalidate.mock.calls.filter(
    ([filters]) =>
      JSON.stringify((filters as { queryKey?: unknown }).queryKey) ===
      JSON.stringify(getGetCurrentConversationQueryKey()),
  )

beforeEach(() => {
  // The card reads the signed-in person (for the year at their location), as the app's cache has.
  installFakeApi('priya')
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] })
  vi.setSystemTime(NOW)
})
afterEach(() => {
  vi.useRealTimers()
})

describe('a pending card’s expiry', () => {
  it('reads the conversation again at the moment the card expires, and not before', () => {
    const { invalidate } = setup(15 * 60_000)

    vi.advanceTimersByTime(15 * 60_000 - 1)
    expect(conversationReads(invalidate)).toHaveLength(0)

    vi.advanceTimersByTime(1)
    expect(conversationReads(invalidate)).toHaveLength(1)
  })

  it('reads again 2 seconds later, at most 3 more times, while the card still reads pending (a clock running ahead)', () => {
    const { invalidate } = setup(1_000)

    vi.advanceTimersByTime(1_000)
    expect(conversationReads(invalidate)).toHaveLength(1)
    vi.advanceTimersByTime(1_999)
    expect(conversationReads(invalidate)).toHaveLength(1)
    vi.advanceTimersByTime(1)
    expect(conversationReads(invalidate)).toHaveLength(2)
    vi.advanceTimersByTime(4_000)
    expect(conversationReads(invalidate)).toHaveLength(4)

    vi.advanceTimersByTime(60 * 60_000)
    expect(conversationReads(invalidate)).toHaveLength(4)
  })

  it('stops retrying once a read shows the card is no longer pending', () => {
    const { invalidate, rerender } = setup(1_000)
    vi.advanceTimersByTime(1_000)
    expect(conversationReads(invalidate)).toHaveLength(1)

    rerender('expired')
    vi.advanceTimersByTime(60_000)

    expect(conversationReads(invalidate)).toHaveLength(1)
  })

  it('reads at once for a card whose time has already passed', () => {
    const { invalidate } = setup(-5_000)
    vi.advanceTimersByTime(0)
    expect(conversationReads(invalidate)).toHaveLength(1)
  })

  it('sets no timer for a card that is not pending', () => {
    const { invalidate } = setup(60_000, 'executed')
    vi.advanceTimersByTime(10 * 60_000)
    expect(conversationReads(invalidate)).toHaveLength(0)
  })

  it('stops the timer when the card goes away', () => {
    const { invalidate, view } = setup(60_000)
    view.unmount()
    vi.advanceTimersByTime(10 * 60_000)
    expect(conversationReads(invalidate)).toHaveLength(0)
  })

  it('shows the time the card expires, and nothing ticks', () => {
    setup(15 * 60_000)
    const before = screen.getByText(/^Expires at/).textContent
    vi.advanceTimersByTime(5 * 60_000)
    expect(screen.getByText(/^Expires at/).textContent).toBe(before)
  })
})

/** The page's side of the expiry: the read the timer asks for turns the card expired. */
function Expiring({
  proposal,
  expose,
}: {
  proposal: ProposalOut
  expose: (expire: () => void) => void
}) {
  const [shown, setShown] = useState(proposal)
  useEffect(() => {
    expose(() => setShown((card) => ({ ...card, status: 'expired' })))
  }, [expose])
  return (
    <>
      <textarea aria-label="Elsewhere" />
      <ProposalCards proposals={[shown]} question="Can I take Friday off?" />
    </>
  )
}

function renderExpiring() {
  const queryClient = createQueryClient({ onUnauthorized: vi.fn<() => void>(), retryDelayMs: 0 })
  let expire = () => {}
  vi.spyOn(queryClient, 'invalidateQueries').mockImplementation(() => {
    expire()
    return Promise.resolve()
  })
  const proposal = proposalOut({ expiresAt: new Date(NOW.getTime() + 60_000).toISOString() })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Expiring
          proposal={proposal}
          expose={(next) => {
            expire = next
          }}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('a card that expires by its timer', () => {
  it('becomes the expired card with "Ask again", and takes focus only if focus was inside it', () => {
    renderExpiring()
    screen.getByRole('button', { name: /^Dismiss/ }).focus()

    act(() => vi.advanceTimersByTime(60_000))

    expect(screen.getByText(/^This card expired after 15 minutes/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask again' })).toHaveFocus()
  })

  it('leaves focus where it is when focus was somewhere else', () => {
    renderExpiring()
    const elsewhere = screen.getByRole('textbox', { name: 'Elsewhere' })
    elsewhere.focus()

    act(() => vi.advanceTimersByTime(60_000))

    expect(screen.getByRole('button', { name: 'Ask again' })).toBeInTheDocument()
    expect(elsewhere).toHaveFocus()
  })
})

describe('yearNow', () => {
  it('is the year it is in the given zone, not UTC’s', () => {
    // 03:00 UTC on January 1 is still December 31 in Oakland.
    const moment = Date.parse('2027-01-01T03:00:00Z')
    expect(yearNow('America/Los_Angeles', moment)).toBe(2026)
    expect(yearNow('UTC', moment)).toBe(2027)
  })
})

describe('a persona switch with a pending card', () => {
  it('clears the card’s timer along with the shell, so no read follows for the new person', () => {
    const { invalidate, view, queryClient } = setup(60_000)

    // The switch clears the cache and remounts everything identity-scoped.
    resetIdentity(queryClient)
    view.unmount()
    vi.advanceTimersByTime(10 * 60_000)

    expect(conversationReads(invalidate)).toHaveLength(0)
  })
})
