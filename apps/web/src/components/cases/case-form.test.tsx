import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  CASE_BULLETS,
  PREFILL,
  SHORT_PREFILL,
  SSN_WORDS,
  wordsOfLength,
} from '@/app/gallery/fixtures/cases'
import { arrow } from '@/test/arrow-key'
import { announce } from '@/lib/announce'
import { CaseForm, type CaseFormProps } from './case-form'

vi.mock('@/lib/announce', () => ({ announce: vi.fn<() => void>(), resetAnnouncer: () => {} }))

type Sent = Parameters<CaseFormProps['onSend']>[0]

function setup(props: Partial<CaseFormProps> = {}) {
  const onSend = vi.fn<(input: Sent) => void>()
  const onCancel = vi.fn<() => void>()
  const user = userEvent.setup()
  const ui = (extra: Partial<CaseFormProps> = {}) => (
    <CaseForm
      variant="panel"
      bullets={CASE_BULLETS}
      prefill={PREFILL}
      onSend={onSend}
      onCancel={onCancel}
      {...props}
      {...extra}
    />
  )
  const view = render(ui())
  return {
    user,
    onSend,
    onCancel,
    rerender: (extra: Partial<CaseFormProps>) => view.rerender(ui(extra)),
  }
}

const words = () => screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Your words' })
const send = () => screen.getByRole('button', { name: /^(Send to HR|Try again|Sending…)$/ })
const choice = (name: string) => screen.getByRole('radio', { name })

describe('CaseForm: the short-reply rule counts as the server does', () => {
  it('treats text that only Python would strip as empty, so no short-reply hint', () => {
    // U+001C is whitespace to Python's strip() and not to JavaScript's trim().
    setup({ prefill: '\u001c\u001c' })
    expect(screen.getByText(/^Say what happened/)).toBeInTheDocument()
  })

  it('treats a lone byte-order mark as text, as Python does, so the hint is the short one', () => {
    // U+FEFF is stripped by JavaScript's trim() and not by Python's.
    setup({ prefill: '\ufeff' })
    expect(screen.getByText(/^Add what happened/)).toBeInTheDocument()
  })
})

describe('CaseForm: describedby', () => {
  it('lists the hint, the count, and the error, and every id is on the page', () => {
    setup({ prefill: SSN_WORDS, validateOnMount: true })
    const ids = words().getAttribute('aria-describedby')!.split(' ')
    expect(ids).toHaveLength(3)
    for (const id of ids) expect(document.getElementById(id)).not.toBeNull()
  })

  it('lists the hint and the count alone when there is no error', () => {
    setup()
    expect(words().getAttribute('aria-describedby')!.split(' ')).toHaveLength(2)
  })
})

describe('CaseForm: how it opens', () => {
  it('puts focus on its heading, an h3 in the panel and an h2 on the page', () => {
    setup()
    const heading = screen.getByRole('heading', { level: 3, name: 'Open a confidential case' })
    expect(heading).toHaveFocus()
    expect(heading).toHaveAttribute('tabindex', '-1')
  })

  it('is an h2 on the page, and leaves focus alone when told to', () => {
    setup({ variant: 'page', focusHeadingOnMount: false })
    const heading = screen.getByRole('heading', { level: 2, name: 'Open a confidential case' })
    expect(heading).not.toHaveFocus()
    // The five lines sit under an h3 there.
    expect(screen.getByRole('heading', { level: 3, name: 'Before you send' })).toBeInTheDocument()
  })

  it('opens with the question verbatim, the count, and nothing chosen', () => {
    setup()
    expect(words()).toHaveValue(PREFILL)
    expect(screen.getByText('46 of 4,000 characters')).toBeInTheDocument()
    expect(screen.getAllByRole('radio')).toHaveLength(5)
    for (const radio of screen.getAllByRole('radio')) expect(radio).not.toBeChecked()
    expect(screen.getByRole('radiogroup', { name: 'What is this about?' })).toBeInTheDocument()
  })

  it('says to add what happened when the prefill is a short reply under 40 characters', () => {
    setup({ prefill: SHORT_PREFILL })
    expect(
      screen.getByText(
        'Add what happened, when, where, and who was involved, as much as you know.',
      ),
    ).toBeInTheDocument()
    expect(words()).toHaveAccessibleDescription(/^Add what happened/)
  })

  it('keeps the ordinary hint for an empty field, and for a prefill of 40 characters or more', () => {
    const hint = 'Say what happened, when, where, and who was involved, as much as you know.'
    for (const [prefill, ordinary] of [
      ['', true],
      ['a'.repeat(39), false],
      ['a'.repeat(40), true],
    ] as const) {
      cleanup()
      setup({ prefill })
      expect(screen.queryByText(hint) !== null, `prefill of ${prefill.length}`).toBe(ordinary)
    }
  })

  it('shows the five lines from the API word for word, under Before you send', () => {
    setup()
    const list = screen.getByRole('list')
    const items = within(list).getAllByRole('listitem')
    expect(items.map((item) => item.textContent)).toEqual(CASE_BULLETS)
    expect(screen.getByRole('heading', { name: 'Before you send' })).toBeInTheDocument()
  })

  it('links only the fifth line’s 911, 988, and the EAP number', () => {
    setup()
    const items = within(screen.getByRole('list')).getAllByRole('listitem')
    for (const plain of items.slice(0, 4))
      expect(within(plain).queryAllByRole('link')).toHaveLength(0)
    const links = within(items[4]!).getAllByRole('link')
    expect(links.map((link) => [link.textContent, link.getAttribute('href')])).toEqual([
      ['call 911', 'tel:911'],
      ['call or text 988', 'tel:988'],
      ['1-800-555-0137', 'tel:+18005550137'],
    ])
  })

  it('renders any other bullets as plain text, whatever they say', () => {
    setup({ bullets: ['A new line.', 'Another with no phone number.'] })
    expect(screen.queryAllByRole('link')).toHaveLength(0)
    expect(screen.getByText('A new line.')).toBeInTheDocument()
  })

  it('is a tinted band with a confidential top border in the panel', () => {
    setup()
    expect(document.querySelector('[data-slot="case-form"]')).toHaveClass(
      'bg-confidential-tint',
      'border-t',
      'border-confidential-border',
    )
  })

  it('is a tinted card with a 16 px radius and a confidential border on the page', () => {
    setup({ variant: 'page', prefill: '' })
    const card = document.querySelector('[data-slot="case-form"]')!
    expect(card).toHaveClass(
      'rounded-xl',
      'border',
      'border-confidential-border',
      'bg-confidential-tint',
    )
    expect(card).not.toHaveClass('border-t')
    expect(screen.getByText('0 of 4,000 characters')).toBeInTheDocument()
  })

  it('never disables Send to HR before it is sending', () => {
    setup()
    expect(send()).toBeEnabled()
    expect(send()).not.toHaveAttribute('aria-disabled')
    expect(send()).not.toHaveAttribute('aria-busy')
  })
})

describe('CaseForm: validation on Send to HR', () => {
  it('shows both errors, marks both fields, links them, and moves focus to the first category option', async () => {
    const { user, onSend } = setup({ prefill: '' })
    await user.click(send())
    expect(onSend).not.toHaveBeenCalled()
    const category = screen.getByText('Choose what this is about.')
    const empty = screen.getByText('Add your words before sending.')
    expect(category.closest('[role="alert"]')).not.toBeNull()
    expect(empty.closest('[role="alert"]')).not.toBeNull()
    const group = screen.getByRole('radiogroup', { name: 'What is this about?' })
    expect(group).toHaveAttribute('aria-invalid', 'true')
    expect(group).toHaveAccessibleDescription('Choose what this is about.')
    expect(words()).toHaveAttribute('aria-invalid', 'true')
    expect(words()).toHaveAccessibleDescription(/Add your words before sending\./)
    expect(choice('Harassment or discrimination')).toHaveFocus()
  })

  it('moves focus to the words when only they are wrong', async () => {
    const { user } = setup({ prefill: SSN_WORDS })
    await user.click(choice('Pay concern'))
    await user.click(send())
    expect(screen.queryByText('Choose what this is about.')).not.toBeInTheDocument()
    expect(
      screen.getByText(
        'That looks like a Social Security or card number. Please take it out before sending.',
      ),
    ).toBeInTheDocument()
    expect(words()).toHaveFocus()
  })

  it('moves focus to the first category option, not the textarea, when both are wrong', async () => {
    const { user } = setup({ prefill: SSN_WORDS })
    await user.click(send())
    expect(choice('Harassment or discrimination')).toHaveFocus()
  })

  it('moves focus to the words when the category is chosen and the words are empty', async () => {
    const { user } = setup({ prefill: '' })
    await user.click(choice('Workplace safety'))
    await user.click(send())
    // Words are empty: the textarea is first invalid, since a category is chosen.
    expect(words()).toHaveFocus()
    expect(screen.getByText('Add your words before sending.')).toBeInTheDocument()
  })

  it('gives the words error the danger border and keeps the counter beside it', async () => {
    const { user } = setup({ prefill: SSN_WORDS })
    await user.click(send())
    expect(words()).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('81 of 4,000 characters')).toBeInTheDocument()
  })

  it('clears an error when its field changes', async () => {
    const { user } = setup({ prefill: '' })
    await user.click(send())
    await user.click(choice('Pay concern'))
    expect(screen.queryByText('Choose what this is about.')).not.toBeInTheDocument()
    expect(screen.getByText('Add your words before sending.')).toBeInTheDocument()
    await user.type(words(), 'My pay was short.')
    expect(screen.queryByText('Add your words before sending.')).not.toBeInTheDocument()
    expect(words()).not.toHaveAttribute('aria-invalid')
  })

  it('sends the category and the words with a UUID once everything passes', async () => {
    const { user, onSend } = setup()
    await user.click(choice('Harassment or discrimination'))
    await user.click(send())
    expect(onSend).toHaveBeenCalledTimes(1)
    expect(onSend).toHaveBeenCalledWith({
      submissionId: expect.stringMatching(
        /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
      ),
      category: 'harassment_discrimination',
      text: PREFILL,
    })
  })

  it('sends the words as typed, not trimmed', async () => {
    const { user, onSend } = setup({ prefill: '  hello  ' })
    await user.click(choice('Pay concern'))
    await user.click(send())
    expect(onSend.mock.calls[0]![0].text).toBe('  hello  ')
  })
})

describe('CaseForm: the limit', () => {
  beforeEach(() => {
    vi.mocked(announce).mockClear()
  })

  it('stops typing at 4,000 characters and says to shorten it', async () => {
    const { user } = setup({ prefill: wordsOfLength(3999) })
    await user.click(words())
    await user.keyboard('{Control>}{End}{/Control}')
    await user.keyboard('xy')
    expect(words().value).toHaveLength(4000)
    expect(words().value.endsWith('x')).toBe(true)
    const count = screen.getByText('4,000 of 4,000 characters. Shorten it to send.')
    expect(count).toHaveClass('font-semibold', 'text-ink')
    expect(count).not.toHaveClass('text-danger')
    expect(count).not.toHaveAttribute('role')
    // Nothing is announced until Send is pressed there.
    expect(announce).not.toHaveBeenCalled()
  })

  it('counts an emoji once, as the server does', () => {
    setup({ prefill: `${wordsOfLength(3999)}😀` })
    expect(screen.getByText('4,000 of 4,000 characters. Shorten it to send.')).toBeInTheDocument()
  })

  it('cuts a paste at the limit, and the counter shows what is left', async () => {
    const { user } = setup({ prefill: wordsOfLength(3990) })
    await user.click(words())
    await user.keyboard('{Control>}{End}{/Control}')
    await user.paste('z'.repeat(50))
    expect([...words().value]).toHaveLength(4000)
    expect(screen.getByText(/^4,000 of 4,000 characters/)).toBeInTheDocument()
  })

  it('cuts a paste in the middle without dropping the existing text after it', async () => {
    const original = wordsOfLength(3990)
    const { user } = setup({ prefill: original })
    words().setSelectionRange(10, 10)
    await user.click(words())
    words().setSelectionRange(10, 10)
    await user.paste('Z'.repeat(50))
    expect(words().value).toBe(original.slice(0, 10) + 'Z'.repeat(10) + original.slice(10))
    // The caret sits after what was kept.
    expect(words().selectionStart).toBe(20)
  })

  it('cuts a paste over a selection without dropping the text around it', async () => {
    const original = wordsOfLength(4000)
    const { user } = setup({ prefill: original })
    await user.click(words())
    words().setSelectionRange(100, 105)
    await user.paste('Z'.repeat(20))
    expect(words().value).toBe(original.slice(0, 100) + 'Z'.repeat(5) + original.slice(105))
  })

  it('lets a deletion stand at the limit', () => {
    setup({ prefill: wordsOfLength(4000) })
    fireEvent.change(words(), { target: { value: wordsOfLength(3990) } })
    expect(screen.getByText('3,990 of 4,000 characters')).toBeInTheDocument()
  })

  it('does not send at the limit, and turns the counter to the error color and announces it', async () => {
    const { user, onSend } = setup({ prefill: wordsOfLength(4000) })
    await user.click(choice('Pay concern'))
    await user.click(send())
    expect(onSend).not.toHaveBeenCalled()
    const count = screen.getByText('4,000 of 4,000 characters. Shorten it to send.')
    expect(count).toHaveClass('text-danger')
    expect(announce).toHaveBeenCalledExactlyOnceWith(
      '4,000 of 4,000 characters. Shorten it to send.',
      'assertive',
    )
    // The announcement is its own message: the counter node keeps its text and takes no role.
    expect(count).not.toHaveAttribute('role')
    expect(words()).toHaveAttribute('aria-invalid', 'true')
    expect(words()).toHaveFocus()
    // Shortening the words ends the error.
    fireEvent.change(words(), { target: { value: wordsOfLength(3990) } })
    expect(screen.getByText('3,990 of 4,000 characters')).not.toHaveClass('text-danger')
  })
})

describe('CaseForm: sending and failing', () => {
  it('shows Sending… as busy and aria-disabled, locks the fields, and ignores clicks', async () => {
    const { user, onSend } = setup({ sending: true, initialCategory: 'pay' })
    const button = send()
    expect(button).toHaveTextContent('Sending…')
    expect(button).toHaveAttribute('aria-busy', 'true')
    expect(button).toHaveAttribute('aria-disabled', 'true')
    expect(words()).toBeDisabled()
    for (const radio of screen.getAllByRole('radio')) expect(radio).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Not now' })).toBeDisabled()
    await user.click(button)
    expect(onSend).not.toHaveBeenCalled()
  })

  it('shows the refusal above the buttons, reads Try again, and keeps the category and words', async () => {
    const { user, rerender } = setup()
    await user.click(choice('Pay concern'))
    await user.type(words(), ' More.')
    rerender({ sendFailed: true })
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Your case wasn’t sent. Please try again.')
    expect(send()).toHaveTextContent('Try again')
    expect(choice('Pay concern')).toBeChecked()
    expect(words()).toHaveValue(`${PREFILL} More.`)
    // Above the buttons in the page order.
    expect(alert.compareDocumentPosition(send()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('moves focus to the message when a send fails, and Try again is next', async () => {
    const { user, rerender } = setup()
    await user.click(choice('Pay concern'))
    rerender({ sending: true })
    rerender({ sending: false, sendFailed: true })
    const message = screen.getByRole('alert').closest('[tabindex="-1"]')!
    expect(message).toHaveFocus()
    await user.tab()
    expect(send()).toHaveFocus()
  })

  it('does not take focus for a failure the form opened with', () => {
    setup({ sendFailed: true, initialCategory: 'pay', focusHeadingOnMount: false })
    expect(document.body).toHaveFocus()
  })

  it('uses one submission ID across a double click and a retry', async () => {
    const { user, onSend, rerender } = setup()
    await user.click(choice('Pay concern'))
    await user.dblClick(send())
    expect(onSend).toHaveBeenCalledTimes(2)
    rerender({ sendFailed: true })
    await user.click(send())
    const ids = onSend.mock.calls.map(([input]) => input.submissionId)
    expect(new Set(ids).size).toBe(1)
    expect(ids).toHaveLength(3)
  })

  it('uses a new submission ID for a form opened afresh', async () => {
    const first = setup()
    await first.user.click(choice('Pay concern'))
    await first.user.click(send())
    document.body.innerHTML = ''
    const second = setup()
    await second.user.click(choice('Pay concern'))
    await second.user.click(send())
    expect(second.onSend.mock.calls[0]![0].submissionId).not.toBe(
      first.onSend.mock.calls[0]![0].submissionId,
    )
  })

  it('calls onCancel for Not now', async () => {
    const { user, onCancel } = setup()
    await user.click(screen.getByRole('button', { name: 'Not now' }))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})

describe('CaseForm: the keyboard', () => {
  it('tabs through the category group, the words, the links, Send, and Not now', async () => {
    const { user } = setup()
    const order: string[] = []
    // From the heading, which holds focus.
    for (let i = 0; i < 7; i += 1) {
      await user.tab()
      const element = document.activeElement!
      order.push(
        element.getAttribute('role') === 'radio'
          ? 'category'
          : element.tagName === 'TEXTAREA'
            ? 'words'
            : (element.textContent ?? '').trim(),
      )
    }
    expect(order).toEqual([
      'category',
      'words',
      'call 911',
      'call or text 988',
      '1-800-555-0137',
      'Send to HR',
      'Not now',
    ])
  })

  it('moves and selects with the arrow keys, one tab stop for the group', async () => {
    const { user } = setup()
    await user.tab()
    expect(choice('Harassment or discrimination')).toHaveFocus()
    await arrow(user, 'ArrowDown')
    expect(choice('Workplace safety')).toHaveFocus()
    expect(choice('Workplace safety')).toBeChecked()
  })
})

describe('CaseForm: a refusal from the server', () => {
  it('shows the personal-data line on the words and focuses them', () => {
    const { rerender } = setup({ initialCategory: 'pay' })
    expect(screen.queryByText(/Social Security or card number/)).not.toBeInTheDocument()
    rerender({ initialCategory: 'pay', refusal: 'personal-data' })
    expect(screen.getByText(/Social Security or card number/)).toBeInTheDocument()
    expect(words()).toHaveAttribute('aria-invalid', 'true')
    expect(words()).toHaveFocus()
  })

  it('shows the empty-words line for an empty refusal', () => {
    const { rerender } = setup({ initialCategory: 'pay' })
    rerender({ initialCategory: 'pay', refusal: 'empty' })
    expect(screen.getByText('Add your words before sending.')).toBeInTheDocument()
  })

  it('clears the line when the person edits the words', async () => {
    const { user, rerender } = setup({ initialCategory: 'pay' })
    rerender({ initialCategory: 'pay', refusal: 'personal-data' })
    await user.type(words(), ' x')
    expect(screen.queryByText(/Social Security or card number/)).not.toBeInTheDocument()
  })
})
