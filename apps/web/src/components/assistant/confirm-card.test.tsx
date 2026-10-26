import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import type { Card } from '@/api/generated'
import {
  CARD_APPROVE,
  CARD_BOOK,
  CARD_CANCEL,
  CARD_CANCEL_SICK,
  CARD_CROSS_YEAR_SICK,
  CARD_DENY,
  CARD_HOLIDAY,
  CARD_SHORT_NOTICE,
  CARD_SICK,
  EXPIRES_AT,
  THIS_YEAR,
  TIME_ZONE,
} from '@/app/gallery/fixtures/timeoff'
import { renderWithRouter } from '@/test/render-with-router'
import { ConfirmCard, type ConfirmCardProps } from './confirm-card'

function props(card: Card, extra: Partial<ConfirmCardProps> = {}): ConfirmCardProps {
  return {
    card,
    status: 'pending',
    canceledReason: null,
    failure: null,
    expiresAt: EXPIRES_AT,
    timeZone: TIME_ZONE,
    thisYear: THIS_YEAR,
    onConfirm: vi.fn<() => void>(),
    onDismiss: vi.fn<() => void>(),
    onAskAgain: vi.fn<() => void>(),
    ...extra,
  }
}

function card(card: Card, extra: Partial<ConfirmCardProps> = {}) {
  return renderWithRouter(<ConfirmCard {...props(card, extra)} />)
}

const outcomeLine = () => document.querySelector<HTMLElement>('[data-slot="confirm-card-outcome"]')!

function facts(): [string, string][] {
  const list = document.querySelector('dl')!
  return [...list.querySelectorAll('dt')].map((term) => [
    term.textContent ?? '',
    (term.nextElementSibling as HTMLElement).textContent ?? '',
  ])
}

describe('ConfirmCard, structure', () => {
  it.each([
    [CARD_BOOK, 'Book PTO'],
    [CARD_SICK, 'Record sick time'],
    [CARD_APPROVE, 'Approve a request'],
    [CARD_DENY, 'Deny a request'],
    [CARD_CANCEL, 'Cancel time off'],
  ] as const)('is a section labeled by its h3 (%#)', (variant, title) => {
    card(variant)
    const section = screen.getByRole('region', { name: title })
    expect(within(section).getByRole('heading', { level: 3, name: title })).toBeInTheDocument()
    expect(section.querySelector('dl')).toBeInTheDocument()
  })

  it('puts the icon in a 32 px tile that screen readers skip', () => {
    card(CARD_BOOK)
    const tile = document.querySelector('[data-slot="confirm-card-tile"]')!
    expect(tile).toHaveAttribute('aria-hidden', 'true')
    expect(tile).toHaveClass('size-8', 'bg-primary-tint')
  })
})

describe('ConfirmCard, a denial while its turn runs', () => {
  it('disables the note, so nothing typed can be lost when the card is drawn again', () => {
    card(CARD_DENY, { turnRunning: true })
    expect(screen.getByRole('textbox', { name: /Note to Zara/ })).toBeDisabled()
  })

  it('leaves the note usable once the turn is over', () => {
    card(CARD_DENY)
    expect(screen.getByRole('textbox', { name: /Note to Zara/ })).toBeEnabled()
  })
})

describe('ConfirmCard, a booking', () => {
  it('lists Type and Dates, with the dates in 600', () => {
    card(CARD_BOOK)
    expect(facts()).toEqual([
      ['Type', 'PTO'],
      ['Dates', 'Friday, October 30'],
    ])
    expect(screen.getByText('Friday, October 30', { selector: 'dd' })).toHaveClass('font-semibold')
  })

  it('shows What this uses with the sources inside it, and the approver line', () => {
    card(CARD_BOOK)
    const preview = screen.getByRole('region', { name: 'What this uses' })
    expect(within(preview).getByText('8 hours (1 day)')).toBeInTheDocument()
    expect(within(preview).getByText(/84 hours \(10\.5 days\) left after this/)).toBeInTheDocument()
    expect(
      within(preview).getByRole('link', { name: 'Source: Handbook §4.1, Paid time off' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Marcus Bell, your manager, reviews PTO requests.')).toBeInTheDocument()
  })

  it('shows dates only on counted lines, and a holiday over the holiday rule', () => {
    card(CARD_HOLIDAY)
    expect(
      screen.getByText('Thursday, November 26 is Thanksgiving, a company holiday'),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Source: Handbook §4.2, Holidays' }),
    ).toBeInTheDocument()
    expect(screen.queryByText('8 hours', { exact: true })).not.toBeInTheDocument()
  })

  it('records sick time with the sick line and one preview', () => {
    card(CARD_SICK)
    expect(facts()[0]).toEqual(['Type', 'Sick time'])
    expect(
      screen.getByText(
        'Sick time is recorded right away, with no approval. Your manager will see it in Coming up.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText(/29 hours of sick leave left this year/)).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Source: Handbook CA-4.3, Sick leave' }),
    ).toBeInTheDocument()
  })

  it('gives a left line per year for sick time across New Year', () => {
    card(CARD_CROSS_YEAR_SICK)
    expect(screen.getByText('16 hours of sick leave left in 2026')).toBeInTheDocument()
    expect(screen.getByText('32 hours of sick leave left in 2027')).toBeInTheDocument()
  })

  it('shows the short-notice warning while pending, and never disables Confirm for it', () => {
    card(CARD_SHORT_NOTICE)
    expect(screen.getByRole('status')).toHaveTextContent(
      'More than 3 days usually needs 2 weeks’ notice. You can still request it.',
    )
    expect(screen.getByRole('button', { name: /^Confirm/ })).not.toHaveAttribute('aria-disabled')
  })

  it('drops the warning once the card is final', () => {
    card(CARD_SHORT_NOTICE, { status: 'executed' })
    expect(screen.queryByText(/usually needs 2 weeks/)).not.toBeInTheDocument()
  })
})

describe('ConfirmCard, a PTO card with no approver', () => {
  it('shows no empty info line', () => {
    card({ ...CARD_BOOK, approver: null })
    const section = screen.getByRole('region', { name: 'Book PTO' })
    for (const paragraph of section.querySelectorAll('p')) {
      expect(paragraph.textContent?.trim()).not.toBe('')
    }
  })
})

describe('ConfirmCard, a decision', () => {
  it('shows the requester, then Type, Dates, Amount, and Balance', () => {
    card(CARD_DENY)
    expect(screen.getByText('Zara Bautista')).toBeInTheDocument()
    expect(screen.getByText('Department Lead, Apparel')).toBeInTheDocument()
    expect(document.querySelector('[data-slot="avatar"]')).toHaveAttribute('data-size', 'lg')
    expect(facts()).toEqual([
      ['Type', 'PTO'],
      ['Dates', 'Monday, November 9 to Tuesday, November 10'],
      ['Amount', '16 hours (2 days)'],
      ['Balance', '62 hours (7.75 days) available now'],
    ])
  })

  it('shows the team coverage and the source', () => {
    card(CARD_DENY)
    expect(
      screen.getByText('Also off: Vikram Morales, Tuesday, November 10 · PTO'),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Source: Handbook §4.1, Paid time off' }),
    ).toBeInTheDocument()
  })

  it('says no one else is off when there is no coverage', () => {
    card(CARD_APPROVE)
    expect(screen.getByText('No one else on your team is off that day.')).toBeInTheDocument()
  })

  it('has a note field on a pending denial only', () => {
    const onNoteChange = vi.fn<() => void>()
    card(CARD_DENY, { note: 'Not that week.', onNoteChange })
    expect(screen.getByRole('textbox', { name: 'Note to Zara (optional)' })).toHaveValue(
      'Not that week.',
    )
  })

  it('has no note field on an approval', () => {
    card(CARD_APPROVE, { note: '', onNoteChange: vi.fn<() => void>() })
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('reads Confirm on an approval and Deny on a denial, both primary', () => {
    const { unmount } = card(CARD_APPROVE)
    expect(screen.getByRole('button', { name: /^Confirm: approve/ })).toHaveTextContent('Confirm')
    unmount()
    card(CARD_DENY)
    const deny = screen.getByRole('button', {
      name: 'Confirm: deny Zara Bautista’s PTO, Monday, November 9 to Tuesday, November 10',
    })
    expect(deny).toHaveTextContent('Deny')
    expect(deny).toHaveClass('bg-primary')
  })
})

describe('ConfirmCard, a cancellation', () => {
  it('shows what goes back, the balance after, and the current status', () => {
    card(CARD_CANCEL)
    expect(facts()).toEqual([
      ['Type', 'PTO'],
      ['Dates', 'Wednesday, December 23'],
      ['Amount', '8 hours (1 day) go back'],
      ['Balance', '100 hours (12.5 days) available after this'],
      ['Status', 'Approved'],
    ])
  })

  it('shows the amount and no balance for sick time', () => {
    card(CARD_CANCEL_SICK)
    expect(facts()).toEqual([
      ['Type', 'Sick time'],
      ['Dates', 'Thursday, October 22'],
      ['Amount', '3 hours'],
      ['Status', 'Recorded'],
    ])
  })

  it('is named for keeping the time off', () => {
    card(CARD_CANCEL)
    expect(
      screen.getByRole('button', { name: 'Dismiss, keep PTO on Wednesday, December 23' }),
    ).toBeInTheDocument()
  })
})

describe('ConfirmCard, pending', () => {
  it('shows the expiry as static text, the AI tag, and the proposal line', () => {
    card(CARD_BOOK)
    expect(screen.getByText('Expires at 3:42 PM')).toBeInTheDocument()
    expect(screen.getByText('AI')).toBeInTheDocument()
    expect(
      screen.getByText('Proposed by the AI. Nothing happens until you confirm.'),
    ).toBeInTheDocument()
  })

  it('has Confirm primary and Dismiss secondary, in that order, named for the action', () => {
    card(CARD_BOOK)
    const footer = document.querySelector('[data-slot="confirm-card-footer"]')!
    const buttons = within(footer as HTMLElement).getAllByRole('button')
    expect(buttons.map((button) => button.textContent)).toEqual(['Confirm', 'Dismiss'])
    expect(buttons[0]).toHaveAccessibleName('Confirm: book PTO on Friday, October 30')
    expect(buttons[1]).toHaveAccessibleName('Dismiss, don’t book PTO on Friday, October 30')
    expect(buttons[0]).toHaveClass('bg-primary')
    expect(buttons[1]).toHaveClass('bg-surface-raised')
    expect(footer).toHaveClass('bg-surface-sunken')
  })

  it('calls Confirm and Dismiss', async () => {
    const onConfirm = vi.fn<() => void>()
    const onDismiss = vi.fn<() => void>()
    const { user } = card(CARD_BOOK, { onConfirm, onDismiss })
    await user.click(screen.getByRole('button', { name: /^Confirm/ }))
    await user.click(screen.getByRole('button', { name: /^Dismiss/ }))
    expect(onConfirm).toHaveBeenCalledOnce()
    expect(onDismiss).toHaveBeenCalledOnce()
  })

  it('tabs through the note, the source chips, Confirm, then Dismiss, as they sit on screen', async () => {
    const { user } = card(CARD_DENY, { note: '', onNoteChange: vi.fn<() => void>() })
    const note = screen.getByRole('textbox')
    const chip = screen.getByRole('link', { name: /Source: Handbook/ })
    expect(note.compareDocumentPosition(chip) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    await user.tab()
    expect(note).toHaveFocus()
    await user.tab()
    expect(chip).toHaveFocus()
    await user.tab()
    expect(screen.getByRole('button', { name: /^Confirm/ })).toHaveFocus()
    await user.tab()
    expect(screen.getByRole('button', { name: /^Dismiss/ })).toHaveFocus()
  })
})

describe('ConfirmCard, while the answer streams', () => {
  it('disables Confirm with aria-disabled, described by the wait line, and ignores it', async () => {
    const onConfirm = vi.fn<() => void>()
    const { user } = card(CARD_BOOK, { turnRunning: true, onConfirm })
    const confirm = screen.getByRole('button', { name: /^Confirm/ })
    expect(confirm).toHaveAttribute('aria-disabled', 'true')
    expect(confirm).toHaveAccessibleDescription('Wait for the answer to finish')
    expect(screen.getByText('Wait for the answer to finish')).toBeVisible()
    await user.click(confirm)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('still lets Dismiss work', async () => {
    const onDismiss = vi.fn<() => void>()
    const { user } = card(CARD_BOOK, { turnRunning: true, onDismiss })
    await user.click(screen.getByRole('button', { name: /^Dismiss/ }))
    expect(onDismiss).toHaveBeenCalledOnce()
  })
})

describe('ConfirmCard, confirming', () => {
  it('shows Confirming… busy and disables Dismiss and the note', () => {
    card(CARD_DENY, { confirming: true, note: 'Not that week.', onNoteChange: vi.fn<() => void>() })
    expect(screen.getByRole('button', { name: 'Confirming…' })).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('button', { name: /^Dismiss/ })).toBeDisabled()
    expect(screen.getByRole('textbox')).toBeDisabled()
  })
})

describe('ConfirmCard, dismissing', () => {
  it('shows Dismissing… busy and disables Confirm and the note', () => {
    card(CARD_DENY, { dismissing: true, note: 'Not that week.', onNoteChange: vi.fn<() => void>() })
    expect(screen.getByRole('button', { name: 'Dismissing…' })).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('button', { name: /^Confirm:/ })).toBeDisabled()
    expect(screen.getByRole('textbox')).toBeDisabled()
  })
})

describe('ConfirmCard, executed', () => {
  it.each([
    [
      CARD_BOOK,
      'Waiting for approval',
      'Requested. Marcus Bell will review it.',
      'View in Time off',
      '/time-off',
    ],
    [CARD_SICK, 'Recorded', 'Recorded.', 'View in Time off', '/time-off'],
    [
      CARD_APPROVE,
      'Approved',
      'Approved. Priya will see it on the Time off page.',
      'View in Approvals',
      '/approvals',
    ],
    [
      CARD_DENY,
      'Denied',
      'Denied. Zara will see it on the Time off page.',
      'View in Approvals',
      '/approvals',
    ],
    [
      CARD_CANCEL,
      'Canceled',
      'Canceled. 8 hours are back in your balance.',
      'View in Time off',
      '/time-off',
    ],
  ] as const)(
    'shows the badge, the line, and the link (%#)',
    (variant, badge, text, link, href) => {
      card(variant, { status: 'executed' })
      const header = document.querySelector('header')!
      expect(within(header).getByText(badge)).toBeInTheDocument()
      expect(screen.queryByText(/^Expires at/)).not.toBeInTheDocument()
      const line = screen.getByRole('status')
      expect(line).toHaveTextContent(text)
      expect(within(line).getByRole('link', { name: link })).toHaveAttribute('href', href)
      expect(line).toHaveAttribute('tabindex', '-1')
      expect(screen.queryByRole('button')).not.toBeInTheDocument()
    },
  )

  it('dresses the line in apricot with a success check, fading in', () => {
    card(CARD_BOOK, { status: 'executed' })
    const line = screen.getByRole('status')
    expect(line).toHaveClass('bg-apricot-tint', 'border-apricot-border')
    expect(line.className).toContain('animate-confirm-in')
    expect(line.querySelector('svg')).toHaveClass('text-success')
  })

  it('keeps the facts at full strength', () => {
    card(CARD_BOOK, { status: 'executed' })
    expect(screen.getByText('PTO', { selector: 'dd' })).not.toHaveClass('text-ink-muted')
    expect(document.querySelector('[data-slot="confirm-card"]')).not.toHaveAttribute('data-muted')
  })

  it('drops the Status row on a cancellation', () => {
    card(CARD_CANCEL, { status: 'executed' })
    expect(facts().map(([term]) => term)).toEqual(['Type', 'Dates', 'Amount', 'Balance'])
  })

  it('says it was Zara’s note on a denial that carried one, and shows the note', () => {
    card(CARD_DENY, { status: 'executed', deniedNote: 'Inventory runs that week.' })
    expect(screen.getByRole('status')).toHaveTextContent(
      'Denied. Zara will see your note on the Time off page.',
    )
    expect(screen.getByText('Your note')).toBeInTheDocument()
    expect(screen.getByText('“Inventory runs that week.”')).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('uses the given link targets', () => {
    card(CARD_BOOK, { status: 'executed', timeOffHref: '/time-off?x=1' })
    expect(screen.getByRole('link', { name: 'View in Time off' })).toHaveAttribute(
      'href',
      '/time-off?x=1',
    )
  })
})

describe('ConfirmCard, failed', () => {
  it('is a danger-tinted alert with the reason, and muted facts', () => {
    card(CARD_BOOK, {
      status: 'failed',
      failure: {
        code: 'overlaps',
        text: 'You already have time off on those days.',
        dates: ['2026-10-30'],
      },
    })
    const alert = outcomeLine()
    expect(alert).toHaveTextContent(
      'Couldn’t book this: you already have time off on Friday, October 30. Nothing was changed.',
    )
    expect(alert).toHaveClass('bg-danger-tint', 'border-danger-border')
    expect(alert).toHaveAttribute('tabindex', '-1')
    expect(alert.querySelector('svg')).toHaveClass('text-danger')
    expect(document.querySelector('[data-slot="confirm-card"]')).toHaveAttribute('data-muted')
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('uses the variant’s verb and the API text for any other code', () => {
    card(CARD_DENY, {
      status: 'failed',
      failure: { code: 'status-changed', text: 'That request changed.' },
    })
    expect(outcomeLine()).toHaveTextContent(
      'Couldn’t deny this. That request changed. Nothing was changed.',
    )
  })
})

describe('ConfirmCard, ended without a change', () => {
  it.each([
    ['canceled', 'dismissed', 'You dismissed this. Nothing was changed.'],
    ['canceled', 'replaced', 'Replaced by a newer card. Nothing was changed.'],
    ['canceled', 'turn-incomplete', 'This card’s answer didn’t finish. Nothing was changed.'],
    ['expired', null, 'This card expired after 15 minutes. Nothing was changed.'],
  ] as const)('shows a neutral status line (%s, %s)', (status, reason, text) => {
    card(CARD_BOOK, { status, canceledReason: reason })
    const line = screen.getByRole('status')
    expect(line).toHaveTextContent(text)
    expect(line).toHaveClass('bg-surface-sunken')
    expect(line).toHaveAttribute('tabindex', '-1')
    expect(line.querySelector('svg')).toHaveClass('text-ink-muted')
    expect(document.querySelector('[data-slot="confirm-card"]')).toHaveAttribute('data-muted')
    expect(document.querySelector('[data-slot="confirm-card-tile"]')).toHaveClass(
      'bg-surface-hover',
      'text-ink-muted',
    )
    expect(screen.queryByText(/^Expires at/)).not.toBeInTheDocument()
  })

  it('offers Ask again only when expired', async () => {
    const onAskAgain = vi.fn<() => void>()
    const { user, unmount } = card(CARD_BOOK, { status: 'expired', onAskAgain })
    await user.click(screen.getByRole('button', { name: 'Ask again' }))
    expect(onAskAgain).toHaveBeenCalledOnce()
    unmount()
    card(CARD_BOOK, { status: 'canceled', canceledReason: 'dismissed' })
    expect(screen.queryByRole('button', { name: 'Ask again' })).not.toBeInTheDocument()
  })
})

function renderMoving(extra: Partial<ConfirmCardProps> = {}, outside = false) {
  const view = (more: Partial<ConfirmCardProps>) => (
    <MemoryRouter>
      {outside && <button>Elsewhere</button>}
      <ConfirmCard {...props(CARD_BOOK, { ...extra, ...more })} />
    </MemoryRouter>
  )
  const result = render(view({}))
  return {
    user: userEvent.setup(),
    update: (more: Partial<ConfirmCardProps>) => result.rerender(view(more)),
  }
}

describe('ConfirmCard, focus', () => {
  it('moves focus to the outcome line when focus was on a button that went away', () => {
    const { update } = renderMoving()
    screen.getByRole('button', { name: /^Confirm/ }).focus()
    update({ status: 'executed' })
    expect(screen.getByRole('status')).toHaveFocus()
  })

  it('moves focus to the outcome after Confirm was pressed, even if focus was left on body', async () => {
    const { user, update } = renderMoving()
    await user.click(screen.getByRole('button', { name: /^Confirm/ }))
    ;(document.activeElement as HTMLElement).blur()
    expect(document.body).toHaveFocus()
    update({ status: 'executed' })
    expect(screen.getByRole('status')).toHaveFocus()
  })

  it('moves focus to the outcome after Dismiss was pressed, even if focus was left on body', async () => {
    const { user, update } = renderMoving()
    await user.click(screen.getByRole('button', { name: /^Dismiss/ }))
    ;(document.activeElement as HTMLElement).blur()
    update({ status: 'canceled', canceledReason: 'dismissed' })
    expect(screen.getByRole('status')).toHaveFocus()
  })

  it('moves focus to the failure alert', () => {
    const { update } = renderMoving()
    screen.getByRole('button', { name: /^Dismiss/ }).focus()
    update({ status: 'failed', failure: { code: 'status-changed', text: 'Changed.' } })
    expect(screen.getByRole('alert')).toHaveFocus()
  })

  it('leaves focus on body when a card is replaced and nobody touched it', () => {
    const { update } = renderMoving()
    expect(document.body).toHaveFocus()
    update({ status: 'canceled', canceledReason: 'replaced' })
    expect(document.body).toHaveFocus()
  })

  it('leaves focus on body when a fresh card expires and nobody touched it', () => {
    const { update } = renderMoving()
    update({ status: 'expired' })
    expect(document.body).toHaveFocus()
  })

  it('does not pull focus from somewhere else on the page', () => {
    const { update } = renderMoving({}, true)
    screen.getByRole('button', { name: 'Elsewhere' }).focus()
    update({ status: 'canceled', canceledReason: 'replaced' })
    expect(screen.getByRole('button', { name: 'Elsewhere' })).toHaveFocus()
  })

  it('moves focus to Ask again when the card expires while focus is inside it', () => {
    const { update } = renderMoving()
    screen.getByRole('button', { name: /^Dismiss/ }).focus()
    update({ status: 'expired' })
    expect(screen.getByRole('button', { name: 'Ask again' })).toHaveFocus()
  })

  it('does not send focus to Ask again just because the card was touched earlier', async () => {
    const { user, update } = renderMoving()
    await user.click(screen.getByRole('button', { name: /^Confirm/ }))
    ;(document.activeElement as HTMLElement).blur()
    update({ status: 'expired' })
    expect(document.body).toHaveFocus()
  })

  it('does not move focus for a card that arrives already final', () => {
    card(CARD_BOOK, { status: 'executed' })
    expect(screen.getByRole('status')).not.toHaveFocus()
  })
})

describe('ConfirmCard, on a phone', () => {
  it('stacks the facts, wraps the footer, and halves the buttons', () => {
    card(CARD_BOOK, { turnRunning: true })
    expect(document.querySelector('dl')!.className).toContain('max-sm:grid-cols-[minmax(0,1fr)]')
    const actions = screen.getByRole('button', { name: /^Confirm/ }).parentElement!
    expect(actions.className).toContain('max-sm:grid-cols-2')
    expect(screen.getByText('Wait for the answer to finish')).toHaveClass('max-sm:col-span-full')
  })
})

describe('ConfirmCard, no figures of its own', () => {
  it('shows a figure only as one of the card’s own labels, or its dates and times', () => {
    card(CARD_DENY)
    let text = document.querySelector('[data-slot="confirm-card"]')!.textContent ?? ''
    const allowed = [
      CARD_DENY.amountLabel,
      CARD_DENY.availableAfterLabel!,
      'Monday, November 9 to Tuesday, November 10',
      'Tuesday, November 10',
      '3:42 PM',
      '0 of 300',
      'Up to 300 characters.',
      'Handbook §4.1 · Paid time off',
    ]
    for (const label of allowed) text = text.replaceAll(label, '')
    expect(text).not.toMatch(/\d/)
  })

  describe('ConfirmCard, a denial note counted as the server counts it', () => {
    it('keeps a note that is only a byte order mark, which Python does not strip', () => {
      card(CARD_DENY, { status: 'executed', deniedNote: '\uFEFF' })
      expect(screen.getByRole('status')).toHaveTextContent('Denied. Zara will see your note')
      expect(screen.getByText('Your note')).toBeInTheDocument()
    })

    it('treats a note of only spaces as no note', () => {
      card(CARD_DENY, { status: 'executed', deniedNote: ' \n ' })
      expect(screen.getByRole('status')).toHaveTextContent(
        'Denied. Zara will see it on the Time off page.',
      )
      expect(screen.queryByText('Your note')).not.toBeInTheDocument()
    })
  })

  describe('ConfirmCard, a press that did not end the card', () => {
    it('does not take focus later when Confirm failed and the card stayed pending', async () => {
      const { user, update } = renderMoving({}, true)
      await user.click(screen.getByRole('button', { name: /^Confirm/ }))
      update({ confirming: true })
      update({ confirming: false })
      ;(document.activeElement as HTMLElement).blur()
      update({ status: 'canceled', canceledReason: 'replaced' })
      expect(document.body).toHaveFocus()
    })

    it('does not take focus later when focus has gone to something outside the card', async () => {
      const { user, update } = renderMoving({}, true)
      await user.click(screen.getByRole('button', { name: /^Dismiss/ }))
      await user.click(screen.getByRole('button', { name: 'Elsewhere' }))
      update({ status: 'canceled', canceledReason: 'replaced' })
      expect(screen.getByRole('button', { name: 'Elsewhere' })).toHaveFocus()
    })
  })

  describe('ConfirmCard, a failure with no reason', () => {
    it('says the card could not be completed, with a single space between sentences', () => {
      card(CARD_BOOK, { status: 'failed', failure: null })
      expect(outcomeLine().textContent).toBe(
        'Couldn’t book this. This card could not be completed. Nothing was changed.',
      )
    })
  })

  describe('ConfirmCard, the balance line', () => {
    it('says available now on a denial, since denying gives the hours back', () => {
      card(CARD_DENY)
      expect(screen.getByText('62 hours (7.75 days) available now')).toBeInTheDocument()
      expect(screen.queryByText(/available after this/)).not.toBeInTheDocument()
    })

    it('says available after this on an approval and a cancellation', () => {
      const { unmount } = card(CARD_APPROVE)
      expect(screen.getByText('84 hours (10.5 days) available after this')).toBeInTheDocument()
      unmount()
      card(CARD_CANCEL)
      expect(screen.getByText('100 hours (12.5 days) available after this')).toBeInTheDocument()
    })
  })

  describe('ConfirmCard, announcing a failure', () => {
    const failure = { code: 'status-changed', text: 'Changed.' }

    it('does not announce a card that is already failed when it first appears', () => {
      card(CARD_BOOK, { status: 'failed', failure })
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      expect(outcomeLine()).toHaveTextContent('Couldn’t book this. Changed. Nothing was changed.')
    })

    it('announces a card that turns failed while it is on the page', () => {
      const { update } = renderMoving()
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      update({ status: 'failed', failure })
      expect(screen.getByRole('alert')).toHaveTextContent('Couldn’t book this.')
    })
  })

  describe('ConfirmCard, a cancellation that gives nothing back', () => {
    it('keeps the request’s own amount in the Amount row, with no "go back"', () => {
      card({ ...CARD_CANCEL, returnsMinutes: 0, returnsLabel: '0 hours' })
      expect(facts()[2]).toEqual(['Amount', '8 hours (1 day)'])
    })
  })

  describe('ConfirmCard, the focus listener', () => {
    it('is attached only while the card is pending', () => {
      const add = vi.spyOn(document, 'addEventListener')
      const focusIn = () => add.mock.calls.filter(([type]) => type === 'focusin').length
      const { update } = renderMoving()
      expect(focusIn()).toBe(1)
      add.mockClear()
      update({ status: 'executed' })
      expect(focusIn()).toBe(0)
      add.mockRestore()
    })

    it('is never attached for a card that is final from the start', () => {
      const add = vi.spyOn(document, 'addEventListener')
      card(CARD_BOOK, { status: 'executed' })
      expect(add.mock.calls.filter(([type]) => type === 'focusin')).toHaveLength(0)
      add.mockRestore()
    })
  })
})
