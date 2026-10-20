import { screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DANA } from '@/test/assistant-fixtures'
import { renderWithRouter } from '@/test/render-with-router'
import { EscalationPanel, type EscalationPanelProps } from './escalation-panel'

const announceMock = vi.hoisted(() => vi.fn<(text: string, politeness?: string) => void>())
vi.mock('@/lib/announce', () => ({ announce: announceMock, resetAnnouncer: () => {} }))

const SENSITIVE_MESSAGE =
  'A person on the HR team should help with this, and they handle it confidentially. Their contact details are below.'
const UNAVAILABLE_MESSAGE =
  "I'm an AI assistant, and I can't answer right now. Please try again in a moment. If you or someone else is in danger, call 911, or call or text 988 to reach the 988 Suicide & Crisis Lifeline. For anything else that can't wait, the HR team can help directly. Their contact details are below."
const CRISIS_MESSAGE = `I'm an AI assistant, and what you wrote sounds serious.

- If you or someone else is in immediate danger, call 911.
- Call or text 988 to reach the 988 Suicide & Crisis Lifeline, or chat at chat.988lifeline.org.
- The Juniper Row EAP: 1-800-555-0137.

You don't have to go through this alone.`

const MESSAGES = {
  sensitive: SENSITIVE_MESSAGE,
  unavailable: UNAVAILABLE_MESSAGE,
  crisis: CRISIS_MESSAGE,
}

function renderPanel(
  props: Partial<EscalationPanelProps> & { kind: EscalationPanelProps['kind'] },
) {
  return renderWithRouter(
    <EscalationPanel message={MESSAGES[props.kind]} contacts={[DANA]} {...props} />,
  )
}

describe.each([
  ['sensitive', 'A person in HR handles this, not the AI'],
  ['crisis', 'Reach a person right now'],
  ['unavailable', "Can't answer right now"],
] as const)('EscalationPanel: %s', (kind, header) => {
  it('is a region labeled by its header', () => {
    renderPanel({ kind })
    const region = screen.getByRole('region', { name: header })
    expect(within(region).getByRole('heading', { level: 2, name: header })).toBeInTheDocument()
  })

  it('is not styled or labeled like an answer: no AI label, sources, or feedback', () => {
    renderPanel({ kind })
    expect(screen.queryByText('AI')).not.toBeInTheDocument()
    expect(screen.queryByText('Sources')).not.toBeInTheDocument()
    expect(screen.queryByText('Was this right?')).not.toBeInTheDocument()
    expect(screen.queryByText('Show your work')).not.toBeInTheDocument()
  })

  it('ends with the HR contacts, after the message', () => {
    renderPanel({ kind })
    const region = screen.getByRole('region', { name: header })
    const contacts = within(region).getByRole('heading', { name: 'HR contacts' })
    expect(within(region).getByRole('link', { name: DANA.workEmail })).toBeInTheDocument()
    expect(within(region).getByRole('link', { name: 'hr@juniperrow.example' })).toBeInTheDocument()
    expect(
      region.querySelector('p, ul')!.compareDocumentPosition(contacts) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })

  it('is a bordered card with a header band', () => {
    renderPanel({ kind })
    const region = screen.getByRole('region', { name: header })
    expect(region).toHaveClass('border', 'overflow-hidden')
    expect(region.querySelector('[data-slot="escalation-band"]')).not.toBeNull()
  })
})

describe('EscalationPanel: the bands', () => {
  it('has an ink band with light text for a crisis, and only for a crisis', () => {
    renderPanel({ kind: 'crisis' })
    const band = document.querySelector('[data-slot="escalation-band"]')!
    expect(band).toHaveClass('bg-ink', 'text-on-primary')
  })

  it.each(['sensitive', 'unavailable'] as const)('has a sunken band for %s', (kind) => {
    renderPanel({ kind })
    const band = document.querySelector('[data-slot="escalation-band"]')!
    expect(band).toHaveClass('bg-surface-sunken', 'text-ink')
    expect(band).not.toHaveClass('bg-ink')
  })

  it("uses red for the can't-answer icon only", () => {
    const { unmount } = renderPanel({ kind: 'unavailable' })
    expect(document.querySelector('[data-slot="escalation-band"] svg')).toHaveClass('text-danger')
    unmount()
    renderPanel({ kind: 'sensitive' })
    expect(document.querySelector('[data-slot="escalation-band"] svg')).not.toHaveClass(
      'text-danger',
    )
    expect(document.querySelector('.text-danger')).toBeNull()
  })
})

describe('EscalationPanel: the message', () => {
  it('shows the unavailable text verbatim, in one paragraph, with 911 and 988 as tel: links', () => {
    renderPanel({ kind: 'unavailable' })
    const region = screen.getByRole('region')
    const paragraph = within(region).getByText(
      (_, element) => element?.textContent === UNAVAILABLE_MESSAGE && element.tagName === 'P',
    )
    expect(paragraph.textContent).toBe(UNAVAILABLE_MESSAGE)
    expect(within(paragraph).getByRole('link', { name: 'call 911' })).toHaveAttribute(
      'href',
      'tel:911',
    )
    expect(within(paragraph).getByRole('link', { name: 'call or text 988' })).toHaveAttribute(
      'href',
      'tel:988',
    )
    expect(within(paragraph).getAllByRole('link')).toHaveLength(2)
    expect(paragraph.querySelector('ul')).toBeNull()
  })

  it('links nothing in the sensitive text', () => {
    renderPanel({ kind: 'sensitive' })
    const paragraph = screen.getByText(SENSITIVE_MESSAGE)
    expect(within(paragraph).queryByRole('link')).not.toBeInTheDocument()
  })

  it('shows the sensitive text verbatim', () => {
    renderPanel({ kind: 'sensitive' })
    expect(screen.getByText(SENSITIVE_MESSAGE)).toBeInTheDocument()
  })

  it('shows a crisis text as paragraphs and a list, with tel: links for 911, 988, and the EAP', () => {
    renderPanel({ kind: 'crisis' })
    const region = screen.getByRole('region')
    // The contacts have their own list, so the crisis list is the first one.
    const list = region.querySelector('ul')!
    expect(within(list).getAllByRole('listitem')).toHaveLength(3)
    expect(within(region).getByRole('link', { name: 'call 911' })).toHaveAttribute(
      'href',
      'tel:911',
    )
    expect(within(region).getByRole('link', { name: 'Call or text 988' })).toHaveAttribute(
      'href',
      'tel:988',
    )
    expect(within(region).getByRole('link', { name: '1-800-555-0137' })).toHaveAttribute(
      'href',
      'tel:+18005550137',
    )
    expect(
      screen.getByText("I'm an AI assistant, and what you wrote sounds serious."),
    ).toBeInTheDocument()
    expect(screen.getByText("You don't have to go through this alone.").tagName).toBe('P')
  })

  it('links the chat address to https in a new tab, safely', () => {
    renderPanel({ kind: 'crisis' })
    const chat = screen.getByRole('link', { name: 'chat.988lifeline.org' })
    expect(chat).toHaveAttribute('href', 'https://chat.988lifeline.org')
    expect(chat).toHaveAttribute('target', '_blank')
    expect(chat).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('opens no other link in a new tab', () => {
    renderPanel({ kind: 'crisis' })
    expect(screen.getByRole('link', { name: 'call 911' })).not.toHaveAttribute('target')
  })

  it('stays plain text when a crisis text has nothing to link', () => {
    renderPanel({ kind: 'crisis', message: 'Please find someone you trust.' })
    expect(screen.getByText('Please find someone you trust.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /911|988|chat/ })).not.toBeInTheDocument()
  })
})

describe('EscalationPanel: the sensitive and unavailable extras', () => {
  it('ends the sensitive panel with a link to the handbook on confidential cases', () => {
    renderPanel({ kind: 'sensitive' })
    const link = screen.getByRole('link', { name: 'How confidential HR cases work, §7.2' })
    expect(link).toHaveAttribute('href', '/handbook/7.2')
    const region = screen.getByRole('region')
    expect(region.lastElementChild!.lastElementChild).toBe(link)
  })

  it('has that link on no other panel', () => {
    renderPanel({ kind: 'unavailable' })
    expect(screen.queryByRole('link', { name: /confidential HR cases/ })).not.toBeInTheDocument()
  })

  it('offers Try again on the unavailable panel, and calls the handler', async () => {
    const onTryAgain = vi.fn<() => void>()
    const { user } = renderPanel({ kind: 'unavailable', onTryAgain })
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onTryAgain).toHaveBeenCalledTimes(1)
  })

  it('has no Try again without a handler, or on another panel', () => {
    const { unmount } = renderPanel({ kind: 'unavailable' })
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
    unmount()
    renderPanel({ kind: 'sensitive', onTryAgain: () => {} })
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })
})

describe('EscalationPanel: its arrival is announced', () => {
  beforeEach(() => {
    announceMock.mockClear()
  })

  it('announces nothing by default, as for a panel restored from the history', () => {
    renderPanel({ kind: 'crisis' })
    renderPanel({ kind: 'sensitive' })
    renderPanel({ kind: 'unavailable' })
    expect(announceMock).not.toHaveBeenCalled()
  })

  it('announces a crisis panel that arrives live once, by its header, assertively', () => {
    renderPanel({ kind: 'crisis', announceOnMount: true })
    expect(announceMock).toHaveBeenCalledExactlyOnceWith('Reach a person right now', 'assertive')
  })

  it.each([
    ['sensitive', 'A person in HR handles this, not the AI'],
    ['unavailable', "Can't answer right now"],
  ] as const)(
    'announces a %s panel that arrives live once, by its header, politely',
    (kind, header) => {
      renderPanel({ kind, announceOnMount: true })
      expect(announceMock).toHaveBeenCalledExactlyOnceWith(header, 'polite')
    },
  )

  it('does not announce again when the panel re-renders', () => {
    const { rerender } = renderPanel({ kind: 'unavailable', announceOnMount: true })
    rerender(
      <MemoryRouter>
        <EscalationPanel kind="unavailable" message="New text." contacts={[DANA]} announceOnMount />
      </MemoryRouter>,
    )
    expect(announceMock).toHaveBeenCalledTimes(1)
  })

  it('carries no live region of its own, which would arrive in the same instant as its text', () => {
    const { container } = renderPanel({ kind: 'crisis', announceOnMount: true })
    expect(
      container.querySelector('[role="alert"], [role="status"], output, [aria-live]'),
    ).toBeNull()
  })

  it('never puts the fixed message in the announcement', () => {
    renderPanel({ kind: 'unavailable', announceOnMount: true })
    expect(announceMock.mock.calls[0]![0]).not.toContain('try again in a moment')
  })
})
