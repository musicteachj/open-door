import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CARD_SICK } from '@/app/gallery/fixtures/timeoff'
import { installFakeApi } from '@/test/fake-api'
import { conversationOut, installAssistantApi, proposalOut, turnOut } from '@/test/fake-assistant'
import { renderApp } from '@/test/render-app'
import { useChatStore } from './store'

// The device is in UTC, where it is already 2027, but the person's store is in Oakland, where it
// is still December 31, 2026: the card reads the year the way the Time off page does.
vi.mock('./proposal-time', async (original) => ({
  ...(await original<typeof import('./proposal-time')>()),
  browserTimeZone: () => 'UTC',
}))

beforeEach(() => {
  useChatStore.setState(useChatStore.getInitialState())
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2027-01-01T04:00:00Z'))
})
afterEach(() => {
  vi.useRealTimers()
})

describe('the confirm card’s current year', () => {
  it('is the year at the person’s location, not the device’s', async () => {
    installFakeApi('priya')
    installAssistantApi({
      conversation: conversationOut({
        turns: [
          turnOut({
            question: 'I am sick today',
            answerText: 'Here is the record.',
            proposals: [
              proposalOut({
                card: CARD_SICK,
                expiresAt: '2027-01-01T05:00:00Z',
              }),
            ],
          }),
        ],
      }),
    })
    renderApp({ at: '/ask' })

    expect(await screen.findByText(/hours of sick leave left this year/)).toBeInTheDocument()
  })
})
