import { delay, http, HttpResponse } from 'msw'
import { act, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MY_CASES, SENT_LINE, WAITING_LIMIT } from '@/app/gallery/fixtures/cases'
import { installFakeApi } from '@/test/fake-api'
import { installFakeCases, statusView } from '@/test/fake-cases'
import { server } from '@/test/msw'
import { renderApp } from '@/test/render-app'
import { useCaseSlots } from './case-slots'

// My cases at /my-cases (Task 36).

vi.mock('@/lib/announce', () => ({ announce: vi.fn<() => void>(), resetAnnouncer: () => {} }))

const CRISIS_TEXT = 'If you are in danger, call 911. The 988 Lifeline is open 24/7.'

function open(
  options: Parameters<typeof installFakeCases>[0] = {},
  persona: 'priya' | 'dana' = 'priya',
) {
  installFakeApi(persona)
  const fake = installFakeCases(options)
  return { ...renderApp({ at: '/my-cases' }), fake }
}

const openButton = () => screen.findByRole('button', { name: 'Open a confidential case' })
const send = () => screen.getByRole('button', { name: /^(Send to HR|Try again)$/ })

beforeEach(() => useCaseSlots.getState().reset())

describe('My cases: the HR contacts', () => {
  it('come from the case texts, and the conversation is never read', async () => {
    // No conversation route is installed: asking for it would fail the test as an unhandled request.
    open({ mine: Array.from({ length: 5 }, (_, i) => statusView({ id: `w-${i}` })) })
    expect(await screen.findByText('Dana Whitfield')).toBeVisible()
  })

  it('show the crisis panel at the full width of the column, not the chat’s 680 px', async () => {
    const { user } = open({ mine: [], crisisText: CRISIS_TEXT })
    await user.click(await openButton())
    await user.click(await screen.findByRole('radio', { name: 'Something else, or not sure' }))
    await user.type(screen.getByRole('textbox', { name: 'Your words' }), 'I want to hurt myself.')
    await user.click(send())
    const crisis = await screen.findByRole('region', { name: 'Reach a person right now' })
    expect(crisis).toHaveClass('max-w-none')
  })
})

describe('My cases: who can see it', () => {
  it('shows HR the Not found page, and asks for no cases', async () => {
    const { fake } = open({}, 'dana')
    expect(
      await screen.findByRole('heading', { level: 1, name: "We couldn't find that page." }),
    ).toBeVisible()
    expect(fake.calls.mine).toBe(0)
  })
})

describe('My cases: the page', () => {
  it('returns focus to the empty list’s button on Not now', async () => {
    const { user } = open({ mine: [] })
    await user.click(await openButton())
    await screen.findByRole('textbox', { name: 'Your words' })
    await user.click(screen.getByRole('button', { name: 'Not now' }))
    expect(await openButton()).toHaveFocus()
  })

  it('has the heading, the intro, and each case as the list shows it', async () => {
    open({ mine: MY_CASES })
    expect(await screen.findByRole('heading', { level: 1, name: 'My cases' })).toBeVisible()
    expect(screen.getByText(/Only the HR team can open them in Open Door/)).toBeVisible()
    const list = await screen.findByRole('list', { name: 'Your cases' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(3)
    expect(within(list).getByText('Sent to HR')).toBeVisible()
    // Status only: nothing is a link.
    expect(within(list).queryByRole('link')).toBeNull()
  })

  it('shows the empty state with its button when nothing was sent', async () => {
    open({ mine: [] })
    expect(await screen.findByText('You haven’t sent HR a case.')).toBeVisible()
    expect(await openButton()).toBeVisible()
  })

  it('opens the form empty, with a button above the list otherwise', async () => {
    const { user } = open({ mine: MY_CASES })
    await user.click(await openButton())
    const words = await screen.findByRole<HTMLTextAreaElement>('textbox', { name: 'Your words' })
    expect(words).toHaveValue('')
    expect(
      screen.getByRole('heading', { level: 2, name: 'Open a confidential case' }),
    ).toHaveFocus()
    // "Not now" returns focus to the button.
    await user.click(screen.getByRole('button', { name: 'Not now' }))
    expect(await openButton()).toHaveFocus()
  })

  it('sends the words with no turn, shows the lead only with no link, and lists the new case first', async () => {
    const { user, fake } = open({ mine: MY_CASES })
    await user.click(await openButton())
    await user.click(await screen.findByRole('radio', { name: 'Pay concern' }))
    await user.type(screen.getByRole('textbox', { name: 'Your words' }), 'My overtime is wrong.')
    await user.click(send())
    const line = await screen.findByText(SENT_LINE.lead)
    expect(line.closest('output')).toHaveFocus()
    expect(screen.queryByText(new RegExp(SENT_LINE.pointer))).toBeNull()
    // The sent line has no link (the sidebar's own My cases item is not in the page).
    expect(within(screen.getByRole('main')).queryByRole('link', { name: /My cases/ })).toBeNull()
    expect(fake.calls.posts).toHaveLength(1)
    expect(fake.calls.posts[0]).toMatchObject({ text: 'My overtime is wrong.', category: 'pay' })
    expect(fake.calls.posts[0]!.turnId).toBeUndefined()
    const list = await screen.findByRole('list', { name: 'Your cases' })
    await vi.waitFor(() => expect(within(list).getAllByRole('listitem')).toHaveLength(4))
    expect(within(list).getAllByRole('listitem')[0]).toHaveTextContent('Pay concern')
  })

  it('ignores a second Send made before the page draws again: one case', async () => {
    const { user, fake } = open({ mine: [] })
    await user.click(await openButton())
    await user.click(await screen.findByRole('radio', { name: 'Pay concern' }))
    await user.type(screen.getByRole('textbox', { name: 'Your words' }), 'My overtime is wrong.')
    const button = send()
    act(() => {
      button.click()
      button.click()
    })
    await screen.findByText(SENT_LINE.lead)
    expect(fake.calls.posts).toHaveLength(1)
  })

  it('refuses a card number in the words as the form does, and sends nothing', async () => {
    const { user, fake } = open({ mine: [] })
    await user.click(await openButton())
    await user.click(await screen.findByRole('radio', { name: 'Pay concern' }))
    await user.type(
      screen.getByRole('textbox', { name: 'Your words' }),
      'My employee number is 123-45-6789.',
    )
    await user.click(send())
    expect(await screen.findByText(/Social Security or card number/)).toBeVisible()
    expect(fake.calls.posts).toEqual([])
  })

  it('shows the server’s personal-data refusal on the words too', async () => {
    const { user } = open({
      mine: [],
      openProblem: { status: 422, type: 'case-personal-data', detail: 'No numbers.' },
    })
    await user.click(await openButton())
    await user.click(await screen.findByRole('radio', { name: 'Pay concern' }))
    await user.type(screen.getByRole('textbox', { name: 'Your words' }), 'Some words.')
    await user.click(send())
    expect(await screen.findByText(/Social Security or card number/)).toBeVisible()
  })

  it('does not bring back a refusal when the form is closed and opened again', async () => {
    const { user } = open({
      mine: [],
      openProblem: { status: 422, type: 'case-personal-data', detail: 'No numbers.' },
    })
    await tryToSend(user)
    await screen.findByText(/Social Security or card number/)
    await user.click(screen.getByRole('button', { name: 'Not now' }))
    await user.click(await openButton())
    await screen.findByRole('textbox', { name: 'Your words' })
    expect(screen.queryByText(/Social Security or card number/)).toBeNull()
    expect(send()).toHaveTextContent('Send to HR')
    expect(
      screen.getByRole('heading', { level: 2, name: 'Open a confidential case' }),
    ).toHaveFocus()
  })

  it('does not bring back a send failure when the form is closed and opened again', async () => {
    const { user } = open({
      mine: [],
      openProblem: { status: 500, type: 'about:blank', detail: 'Broke.' },
    })
    await tryToSend(user)
    await screen.findByText('Your case wasn’t sent. Please try again.')
    await user.click(screen.getByRole('button', { name: 'Not now' }))
    await user.click(await openButton())
    await screen.findByRole('textbox', { name: 'Your words' })
    expect(screen.queryByText('Your case wasn’t sent. Please try again.')).toBeNull()
    expect(send()).toHaveTextContent('Send to HR')
    expect(
      screen.getByRole('heading', { level: 2, name: 'Open a confidential case' }),
    ).toHaveFocus()
  })

  it('treats a conflict on the submission as already sent: no error, the form closes, the case is listed', async () => {
    const { user } = open({
      mine: [],
      openProblem: { status: 409, type: 'case-submission-conflict', detail: 'Already sent.' },
      saveBeforeProblem: true,
    })
    await tryToSend(user)
    const list = await screen.findByRole('list', { name: 'Your cases' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(1)
    expect(screen.queryByRole('textbox', { name: 'Your words' })).toBeNull()
    expect(screen.queryByText('Your case wasn’t sent. Please try again.')).toBeNull()
  })

  it('lists a case the server saved even though its answer was a failure', async () => {
    const { user } = open({
      mine: [],
      openProblem: { status: 500, type: 'about:blank', detail: 'Broke.' },
      saveBeforeProblem: true,
    })
    await tryToSend(user)
    await screen.findByText('Your case wasn’t sent. Please try again.')
    const list = await screen.findByRole('list', { name: 'Your cases' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(1)
  })

  it('shows the crisis text after the sent line when the safety check routed the words', async () => {
    const { user } = open({ mine: [], crisisText: CRISIS_TEXT })
    await user.click(await openButton())
    await user.click(await screen.findByRole('radio', { name: 'Something else, or not sure' }))
    await user.type(screen.getByRole('textbox', { name: 'Your words' }), 'I want to hurt myself.')
    await user.click(send())
    const sent = await screen.findByText(SENT_LINE.lead)
    const crisis = await screen.findByRole('region', { name: 'Reach a person right now' })
    expect(within(crisis).getByText(/call 911/)).toBeVisible()
    expect(sent.compareDocumentPosition(crisis) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    // HR's contacts come with it, from the conversation.
    expect(within(crisis).getByText('Dana Whitfield')).toBeVisible()
  })

  it('shows the limit line with the HR contacts and no link when five are waiting', async () => {
    open({ mine: Array.from({ length: 5 }, (_, i) => statusView({ id: `w-${i}` })) })
    expect(await screen.findByText(WAITING_LIMIT)).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Open a confidential case' })).toBeNull()
    expect(screen.queryByRole('link', { name: /your cases/i })).toBeNull()
    expect(screen.getByText('Dana Whitfield')).toBeVisible()
  })

  async function tryToSend(user: ReturnType<typeof open>['user'], then?: () => void) {
    await user.click(await openButton())
    await user.click(await screen.findByRole('radio', { name: 'Pay concern' }))
    await user.type(screen.getByRole('textbox', { name: 'Your words' }), 'Some words.')
    then?.()
    await user.click(send())
  }
  const FIVE = Array.from({ length: 5 }, (_, i) => statusView({ id: `w-${i}` }))

  it('shows the limit line when the server refuses the send for it', async () => {
    const { user, fake } = open({
      mine: MY_CASES,
      openProblem: { status: 409, type: 'case-waiting-limit', detail: 'Five.' },
    })
    // The server refuses because five are waiting, and the list read again says so.
    await tryToSend(user, () => (fake.state.mine = FIVE))
    const line = await screen.findByText(WAITING_LIMIT)
    expect(line.closest('output')).toHaveFocus()
  })

  it('drops the limit line when the list read again shows fewer than five waiting', async () => {
    const { user } = open({
      mine: MY_CASES,
      openProblem: { status: 409, type: 'case-waiting-limit', detail: 'Five.' },
    })
    // The list read after the refusal is slow, so the refusal alone holds the line meanwhile.
    await tryToSend(user, () =>
      server.use(
        http.get(`${window.location.origin}/api/v1/cases/mine`, async () => {
          await delay(150)
          return HttpResponse.json({ items: MY_CASES })
        }),
      ),
    )
    expect(await screen.findByText(WAITING_LIMIT)).toBeVisible()
    // Then the list shows fewer than five: the line is not kept.
    expect(await openButton()).toBeVisible()
    expect(screen.queryByText(WAITING_LIMIT)).toBeNull()
  })
})
