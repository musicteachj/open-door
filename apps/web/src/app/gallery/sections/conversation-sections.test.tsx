import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { renderWithRouter } from '@/test/render-with-router'
import { ConversationSections } from './conversation-sections'

// The browser tests address each state by its heading's id, so the ids are part of the contract.
// They are in the page order of e2e/gallery-ids.ts, which follows the States table in
// docs/design/screens/07-conversation/notes.md.
const IDS = [
  'conversation-cited-answer',
  'conversation-source-panel',
  'conversation-streaming-searching',
  'conversation-streaming-text',
  'conversation-streaming-progress-note',
  'conversation-stopped',
  'conversation-show-your-work',
  'conversation-show-your-work-routed',
  'conversation-feedback-yes',
  'conversation-feedback-no',
  'conversation-feedback-thanks',
  'conversation-other-state',
  'conversation-not-found',
  'conversation-refusal',
  'conversation-sensitive',
  'conversation-crisis',
  'conversation-error-midstream',
  'conversation-cant-answer',
  'conversation-send-error',
  'conversation-budget-sandbox',
  'conversation-budget-daily',
  'conversation-length-hint',
  'conversation-personal-data',
  'conversation-long-conversation',
]

const state = (id: string) =>
  document.querySelector<HTMLElement>(`section[aria-labelledby="${id}"]`)!

function renderSections() {
  return renderWithRouter(<ConversationSections />)
}

describe('ConversationSections: the states', () => {
  it('has a heading with a stable id for every state, in the design order', () => {
    const { container } = renderSections()
    const found = [...container.querySelectorAll('h3[id^="conversation-"]')].map((h) => h.id)
    expect(found).toEqual(IDS)
  })

  it('puts each state in a section labeled by its heading', () => {
    renderSections()
    const missing = IDS.filter((id) => state(id) === null)
    expect(missing).toEqual([])
  })
})

describe('ConversationSections: what each state shows', () => {
  it('shows a cited answer with markers, chips, feedback, and a collapsed trace', () => {
    renderSections()
    const section = state('conversation-cited-answer')
    expect(within(section).getByText('AI')).toBeInTheDocument()
    expect(within(section).getAllByRole('button', { name: /^Source 1: / })).toHaveLength(4)
    expect(within(section).getByText('Sources')).toBeInTheDocument()
    expect(within(section).getByText('Was this right?')).toBeInTheDocument()
    expect(within(section).getByRole('button', { name: 'Show your work' })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
    expect(within(section).getByRole('textbox', { name: 'Ask Open Door' })).toBeInTheDocument()
  })

  it('numbers the markers by section, as the design does', () => {
    renderSections()
    const section = state('conversation-cited-answer')
    const markers = [...section.querySelectorAll('[data-slot="citation-marker"]')]
    expect(markers.map((marker) => marker.textContent)).toEqual(['1', '1', '1', '2'])
  })

  it('starts the source panel closed, and opens the real passage beside a marker', async () => {
    renderSections()
    const section = state('conversation-source-panel')
    expect(within(section).queryByRole('complementary')).not.toBeInTheDocument()
    const markers = within(section).getAllByRole('button', { name: /^Source 1: / })
    await userEvent.click(markers[2]!)
    expect(within(section).getByRole('complementary', { name: 'Handbook passage' })).toBeVisible()
    // Only the marker for the passage that is open is active. The fourth button is the section's
    // chip, which is expanded too: a chip shows open while any passage of its section is.
    expect(markers.map((marker) => marker.getAttribute('aria-expanded'))).toEqual([
      'false',
      'false',
      'true',
      'true',
    ])
  })

  it('puts the open source panel in its own frame after the conversation frame, in one state', async () => {
    renderSections()
    const section = state('conversation-source-panel')
    await userEvent.click(within(section).getAllByRole('button', { name: /^Source 1: / })[2]!)
    const wrapper = section.querySelector('[data-slot="conversation-state"]')!
    const frame = wrapper.querySelector('[data-slot="conversation-frame"]')!
    const panelFrame = wrapper.querySelector('[data-slot="source-panel-frame"]')!
    expect(frame.contains(panelFrame)).toBe(false)
    expect(
      frame.compareDocumentPosition(panelFrame) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(
      within(panelFrame as HTMLElement).getByRole('complementary', { name: 'Handbook passage' }),
    ).toBeVisible()
  })

  it('wraps every state in one conversation state', () => {
    renderSections()
    const wrong = IDS.filter(
      (id) => state(id).querySelectorAll('[data-slot="conversation-state"]').length !== 1,
    )
    expect(wrong).toEqual([])
  })

  it('shows the status line before any text, with Stop in the composer', () => {
    renderSections()
    const section = state('conversation-streaming-searching')
    expect(section.querySelector('[data-slot="status-line"]')).toHaveTextContent(
      'Searching the handbook…',
    )
    expect(within(section).getByRole('button', { name: 'Stop' })).toBeInTheDocument()
    expect(within(section).queryByText('Sources')).not.toBeInTheDocument()
  })

  it('shows text arriving with a marker and no sources yet', () => {
    renderSections()
    const section = state('conversation-streaming-text')
    expect(section.querySelector('[data-slot="answer-live"]')).toHaveAttribute('aria-busy', 'true')
    expect(within(section).getAllByRole('button', { name: /^Source 1: / })).toHaveLength(1)
    expect(within(section).queryByText('Sources')).not.toBeInTheDocument()
  })

  it('shows finished steps and the current one in the progress note', () => {
    renderSections()
    const status = state('conversation-streaming-progress-note').querySelector<HTMLElement>(
      '[data-slot="status-line"]',
    )!
    expect(
      within(status)
        .getAllByRole('listitem')
        .map((item) => item.textContent),
    ).toEqual([
      'Searched the handbook: sick leave',
      'Read §4.3 Sick leave',
      'Searching the handbook again…',
    ])
  })

  it('shows a stopped answer with Ask again, and Ask in the composer', () => {
    renderSections()
    const section = state('conversation-stopped')
    expect(within(section).getByText('Stopped')).toBeInTheDocument()
    expect(within(section).getByRole('button', { name: 'Ask again' })).toBeInTheDocument()
    expect(within(section).getByRole('button', { name: 'Ask' })).toBeInTheDocument()
  })

  it('opens "Show your work" expanded, with the safety check, the tools, and the sections', () => {
    renderSections()
    const section = state('conversation-show-your-work')
    expect(within(section).getByRole('button', { name: 'Show your work' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    expect(within(section).getByText('Safety check: no concerns')).toBeVisible()
    expect(within(section).getByText('Tools called')).toBeVisible()
    expect(within(section).getByText('Cited as 1')).toBeVisible()
    expect(within(section).getAllByText('Not cited')).toHaveLength(2)
  })

  it('shows a sensitive turn as the answer, the HR panel, and a routed trace', () => {
    renderSections()
    const section = state('conversation-show-your-work-routed')
    const order = [
      section.querySelector('[data-slot="assistant-message"]'),
      section.querySelector('[data-slot="escalation-panel"]'),
      section.querySelector('[data-slot="work-trace-toggle"]'),
    ]
    expect(order.every(Boolean)).toBe(true)
    order.slice(1).forEach((node, index) => {
      expect(order[index]!.compareDocumentPosition(node!) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(
        Node.DOCUMENT_POSITION_FOLLOWING,
      )
    })
    expect(within(section).getByText('Routed to HR guidance')).toBeVisible()
    expect(
      within(section).getByText('Questions like this also go to a person on the HR team.'),
    ).toBeVisible()
  })

  it('shows the thank-you for a Yes and after a reason, as the same line', () => {
    renderSections()
    for (const id of ['conversation-feedback-yes', 'conversation-feedback-thanks']) {
      const section = state(id)
      expect(within(section).getByText('Thanks for the feedback.')).toBeInTheDocument()
      expect(within(section).queryByText('Was this right?')).not.toBeInTheDocument()
    }
  })

  it('shows the reason form with the typed reason and its count', () => {
    renderSections()
    const section = state('conversation-feedback-no')
    expect(within(section).getByRole('textbox', { name: /What was wrong/ })).toHaveValue(
      "It didn't say whether I need a doctor's note.",
    )
    expect(within(section).getByText('45 of 500 characters')).toBeInTheDocument()
  })

  it("shows another state's policy as Mateo", () => {
    renderSections()
    const section = state('conversation-other-state')
    expect(
      within(section).getByText(/What’s the overtime rule in California\?/),
    ).toBeInTheDocument()
    expect(within(section).getByText(/Austin warehouse in Texas/)).toBeInTheDocument()
  })

  it('shows a not-found answer with no sources and the HR contacts card', () => {
    renderSections()
    const section = state('conversation-not-found')
    expect(within(section).getByText(/I couldn’t find that in the handbook/)).toBeInTheDocument()
    expect(within(section).queryByText('Sources')).not.toBeInTheDocument()
    const contacts = section.querySelector('[data-slot="hr-contacts"]')!
    expect(within(contacts as HTMLElement).getByText('Dana Whitfield')).toBeInTheDocument()
    expect(
      within(contacts as HTMLElement).getByText('HR Business Partner · Denver HQ'),
    ).toBeInTheDocument()
    expect(within(contacts as HTMLElement).getByText('Shared inbox')).toBeInTheDocument()
  })

  it('shows a refusal as an answer, with a source and a link to the directory', () => {
    renderSections()
    const section = state('conversation-refusal')
    expect(
      within(section).getByText(/I can’t share another employee’s home address/),
    ).toBeInTheDocument()
    expect(within(section).getByRole('link', { name: 'Directory' })).toHaveAttribute(
      'href',
      '/directory/',
    )
    expect(within(section).getAllByRole('button', { name: /^Source 1: / }).length).toBeGreaterThan(
      0,
    )
  })

  it('shows the sensitive answer first, then the panel, then feedback is not under the panel', () => {
    renderSections()
    const section = state('conversation-sensitive')
    const message = section.querySelector('[data-slot="assistant-message"]')!
    const panel = section.querySelector('[data-slot="escalation-panel"]')!
    expect(message.compareDocumentPosition(panel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(within(panel as HTMLElement).queryByText('Was this right?')).not.toBeInTheDocument()
    expect(within(section).getByRole('button', { name: 'Show your work' })).toBeInTheDocument()
  })

  it("puts the sensitive answer's marker at the end of its sentence, not in the middle of it", () => {
    renderSections()
    const marker = state('conversation-sensitive').querySelector('[data-slot="citation-marker"]')!
    expect(marker.previousSibling?.textContent).toMatch(/confidentially\.\s*$/)
  })

  it('shows the crisis panel with its fixed text, and no AI label of its own', () => {
    renderSections()
    const panel = state('conversation-crisis').querySelector('[data-slot="escalation-panel"]')!
    expect(panel).toHaveAttribute('data-kind', 'crisis')
    expect(within(panel as HTMLElement).getByRole('link', { name: 'call 911' })).toHaveAttribute(
      'href',
      'tel:911',
    )
    expect(within(panel as HTMLElement).queryByText('AI')).not.toBeInTheDocument()
    expect(state('conversation-crisis').querySelector('[data-slot="assistant-message"]')).toBeNull()
  })

  it("shows the API's own error text in the message, with Retry", () => {
    renderSections()
    const section = state('conversation-error-midstream')
    expect(within(section).getByRole('alert')).toHaveTextContent(
      "Something went wrong on our side, and I couldn't finish that. Please try again, or ask the HR team.",
    )
    expect(within(section).getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('shows "can\'t answer right now" with 911 and 988 as links and Try again', () => {
    renderSections()
    const panel = state('conversation-cant-answer').querySelector('[data-slot="escalation-panel"]')!
    expect(panel).toHaveAttribute('data-kind', 'unavailable')
    expect(
      within(panel as HTMLElement).getByRole('link', { name: 'call or text 988' }),
    ).toHaveAttribute('href', 'tel:988')
    expect(
      within(panel as HTMLElement).getByRole('button', { name: 'Try again' }),
    ).toBeInTheDocument()
  })

  it('shows the send error under a streaming composer, with the draft kept', () => {
    renderSections()
    const section = state('conversation-send-error')
    expect(within(section).getByRole('alert')).toHaveTextContent(
      "I'm still answering your last question.",
    )
    expect(within(section).getByRole('textbox', { name: 'Ask Open Door' })).toHaveValue(
      'Can I carry unused days over?',
    )
    expect(within(section).getByRole('button', { name: 'Stop' })).toBeInTheDocument()
  })

  it.each([
    ['conversation-budget-sandbox', 'This demo sandbox has reached its limit', true],
    [
      'conversation-budget-daily',
      "The demo's daily limit for the assistant has been reached.",
      false,
    ],
  ])('shows the %s banner over a disabled composer', (id, text, hasButton) => {
    renderSections()
    const section = state(id)
    expect(section.querySelector('[data-slot="banner"]')).toHaveTextContent(text)
    expect(within(section).getByRole('link', { name: 'call 911' })).toHaveAttribute(
      'href',
      'tel:911',
    )
    expect(within(section).getByRole('textbox', { name: 'Ask Open Door' })).toBeDisabled()
    expect(within(section).queryByRole('button', { name: 'Start a new sandbox' }) !== null).toBe(
      hasButton,
    )
    expect(within(section).getByRole('link', { name: 'Handbook' })).toBeInTheDocument()
  })

  it('shows the length hint for a draft of 1,962 characters', () => {
    renderSections()
    const section = state('conversation-length-hint')
    const box = within(section).getByRole('textbox', {
      name: 'Ask Open Door',
    }) as HTMLTextAreaElement
    expect([...box.value.trim()]).toHaveLength(1962)
    expect(within(section).getByText('1,962 of 2,000 characters')).toBeInTheDocument()
  })

  it('shows the personal-data warning as an alert', () => {
    renderSections()
    const section = state('conversation-personal-data')
    expect(within(section).getByRole('alert')).toHaveTextContent(
      "That looks like a Social Security or card number. Please take it out; I can't take those.",
    )
  })

  it('shows two turns and the long-conversation notice', () => {
    renderSections()
    const section = state('conversation-long-conversation')
    expect(section.querySelectorAll('[data-slot="user-message"]')).toHaveLength(2)
    expect(section.querySelectorAll('[data-slot="assistant-message"]')).toHaveLength(2)
    expect(section.querySelector('[data-slot="composer-notice"]')).toHaveTextContent(
      'This conversation is getting long',
    )
  })
})

describe('ConversationSections: the chips name the chapter, as the API does', () => {
  const chips = (id: string) =>
    [...state(id).querySelectorAll('[data-slot="source-chip"]')].map((chip) =>
      chip.textContent?.replace(/^\d/, '').trim(),
    )

  it('uses the chapter name for a company section and the addendum name for an addendum', () => {
    renderSections()
    expect(chips('conversation-cited-answer')).toEqual([
      'Handbook CA-4.3 · California addendum',
      'Handbook §4.3 · Time off',
    ])
    expect(chips('conversation-other-state')).toEqual([
      'Handbook CA-3.2 · California addendum',
      'Handbook §3.2 · Hours and pay',
    ])
    expect(chips('conversation-refusal')).toEqual([
      'Handbook §7.1 · Privacy and confidential cases',
    ])
    expect(chips('conversation-sensitive')).toEqual(['Handbook §2.3 · Working here'])
    expect(chips('conversation-long-conversation')).toContain('Handbook §4.2 · Time off')
  })

  it('names the same groups in "Show your work"', () => {
    renderSections()
    const panel = state('conversation-show-your-work').querySelector(
      '[data-slot="work-trace-panel"]',
    )!
    expect(panel).toHaveTextContent('Paid time off · Time off')
    expect(panel).not.toHaveTextContent('Company handbook')
    expect(state('conversation-show-your-work-routed')).toHaveTextContent(
      'How confidential HR cases work · Privacy and confidential cases',
    )
  })
})

describe('ConversationSections: the interactive pieces', () => {
  it('moves focus into the reason box on No, and back to No on Cancel', async () => {
    renderSections()
    const section = state('conversation-cited-answer')
    await userEvent.click(within(section).getByRole('button', { name: 'No' }))
    expect(within(section).getByRole('textbox', { name: /What was wrong/ })).toHaveFocus()
    await userEvent.click(within(section).getByRole('button', { name: 'Cancel' }))
    expect(within(section).getByRole('button', { name: 'No' })).toHaveFocus()
  })

  it('sends a Yes and shows the thank-you', async () => {
    renderSections()
    const section = state('conversation-cited-answer')
    await userEvent.click(within(section).getByRole('button', { name: 'Yes' }))
    expect(within(section).getByText('Thanks for the feedback.')).toHaveFocus()
  })

  it('toggles "Show your work"', async () => {
    renderSections()
    const toggle = within(state('conversation-cited-answer')).getByRole('button', {
      name: 'Show your work',
    })
    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
  })

  it('types into a composer', async () => {
    renderSections()
    const box = within(state('conversation-cited-answer')).getByRole('textbox', {
      name: 'Ask Open Door',
    })
    await userEvent.type(box, 'Hello')
    expect(box).toHaveValue('Hello')
  })

  it('ends the stream on Stop without sending the draft, and keeps the draft', async () => {
    renderSections()
    const section = state('conversation-send-error')
    const frame = section.querySelector('[data-submit-count]')!
    expect(frame).toHaveAttribute('data-submit-count', '0')
    await userEvent.click(within(section).getByRole('button', { name: 'Stop' }))
    expect(within(section).getByRole('button', { name: 'Ask' })).toBeInTheDocument()
    expect(frame).toHaveAttribute('data-submit-count', '0')
    expect(within(section).getByRole('textbox', { name: 'Ask Open Door' })).toHaveValue(
      'Can I carry unused days over?',
    )
    expect(screen.queryAllByText('Stopped').length).toBeGreaterThan(0)
  })
})
