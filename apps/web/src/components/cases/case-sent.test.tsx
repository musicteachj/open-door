import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SENT_LINE, WAITING_LIMIT } from '@/app/gallery/fixtures/cases'
import { DANA } from '@/test/assistant-fixtures'
import { renderWithRouter } from '@/test/render-with-router'
import { CaseSent, type CaseSentProps } from './case-sent'
import { MY_CASES_LINK, YOUR_CASES_LINK } from './labels'

const sentLine = `${SENT_LINE.lead} ${SENT_LINE.pointer}`

describe('CaseSent: links', () => {
  it('renders no link, and nothing to /my-cases, unless the caller passes one', () => {
    // `link` is a required prop; a caller that leaves it out at runtime still gets no link.
    const sent = {
      variant: 'panel',
      state: 'sent',
      sentLine: SENT_LINE,
    } as unknown as CaseSentProps
    const limit = {
      variant: 'panel',
      state: 'limit',
      limitLine: WAITING_LIMIT,
    } as unknown as CaseSentProps
    for (const props of [sent, limit]) {
      const { container, unmount } = renderWithRouter(<CaseSent {...props} />)
      expect(screen.queryByRole('link')).toBeNull()
      expect(container.innerHTML).not.toContain('/my-cases')
      unmount()
    }
  })
})

describe('CaseSent: sent in the panel', () => {
  it('is a status with the API’s line word for word, and takes focus', () => {
    renderWithRouter(
      <CaseSent variant="panel" state="sent" sentLine={SENT_LINE} link={MY_CASES_LINK} />,
    )
    const status = screen.getByRole('status')
    expect(status).toHaveAttribute('tabindex', '-1')
    expect(status).toHaveFocus()
    expect(status.querySelector('p')).toHaveTextContent(sentLine, { normalizeWhitespace: false })
    expect(status.querySelector('p')!.textContent).toBe(sentLine)
  })

  it('leaves focus alone for a frame that is only shown', () => {
    renderWithRouter(
      <CaseSent
        variant="panel"
        state="sent"
        sentLine={SENT_LINE}
        link={MY_CASES_LINK}
        focusOnMount={false}
      />,
    )
    expect(document.body).toHaveFocus()
  })

  it('has the lock, no check or celebration, and the View in My cases link after the line', () => {
    renderWithRouter(
      <CaseSent variant="panel" state="sent" sentLine={SENT_LINE} link={MY_CASES_LINK} />,
    )
    const status = screen.getByRole('status')
    expect(status.querySelector('svg.lucide-lock')).not.toBeNull()
    expect(status.querySelector('.lucide-circle-check, .lucide-check')).toBeNull()
    const link = within(status).getByRole('link', { name: 'View in My cases' })
    expect(link).toHaveAttribute('href', '/my-cases')
    expect(
      status.querySelector('p')!.compareDocumentPosition(link) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })

  it('is the next tab stop after the status', async () => {
    const { user } = renderWithRouter(
      <CaseSent variant="panel" state="sent" sentLine={SENT_LINE} link={MY_CASES_LINK} />,
    )
    await user.tab()
    expect(screen.getByRole('link', { name: 'View in My cases' })).toHaveFocus()
  })

  it('takes another link for HR, whose pointer names Cases', () => {
    renderWithRouter(
      <CaseSent
        variant="panel"
        state="sent"
        sentLine={{ ...SENT_LINE, pointer: 'You can see its status in Cases.' }}
        link={{ to: '/cases', label: 'View in Cases' }}
      />,
    )
    expect(screen.getByRole('link', { name: 'View in Cases' })).toHaveAttribute('href', '/cases')
  })

  it('is a tinted band with a confidential top border', () => {
    renderWithRouter(
      <CaseSent variant="panel" state="sent" sentLine={SENT_LINE} link={MY_CASES_LINK} />,
    )
    expect(document.querySelector('[data-slot="case-sent"]')).toHaveClass(
      'bg-confidential-tint',
      'border-t',
      'border-confidential-border',
    )
  })
})

describe('CaseSent: sent on My cases', () => {
  it('shows the lead alone, with no pointer and no link, in a tinted card', () => {
    renderWithRouter(<CaseSent variant="page" state="sent" sentLine={SENT_LINE} link={null} />)
    const status = screen.getByRole('status')
    expect(status.querySelector('p')!.textContent).toBe(SENT_LINE.lead)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(document.querySelector('[data-slot="case-sent"]')).toHaveClass(
      'rounded-xl',
      'bg-confidential-tint',
    )
    expect(status).toHaveFocus()
  })
})

describe('CaseSent: the limit line replacing the form', () => {
  it('takes focus on mount when asked, so focus is not lost with the form', () => {
    renderWithRouter(
      <CaseSent variant="panel" state="limit" limitLine={WAITING_LIMIT} link={null} focusOnMount />,
    )
    const status = screen.getByRole('status')
    expect(status).toHaveAttribute('tabindex', '-1')
    expect(status).toHaveFocus()
  })

  it('takes none otherwise, and then needs no tabindex', () => {
    renderWithRouter(
      <CaseSent variant="panel" state="limit" limitLine={WAITING_LIMIT} link={null} />,
    )
    expect(document.body).toHaveFocus()
    expect(screen.getByRole('status')).not.toHaveAttribute('tabindex')
  })
})

describe('CaseSent: the waiting limit', () => {
  it('says the API’s limit line, links to your cases in the panel, and takes no focus', () => {
    renderWithRouter(
      <CaseSent variant="panel" state="limit" limitLine={WAITING_LIMIT} link={YOUR_CASES_LINK} />,
    )
    const status = screen.getByRole('status')
    expect(status).toHaveTextContent(WAITING_LIMIT)
    expect(within(status).getByRole('link', { name: 'View your cases' })).toHaveAttribute(
      'href',
      '/my-cases',
    )
    expect(status).not.toHaveAttribute('tabindex')
    expect(document.body).toHaveFocus()
  })

  it('has no link on My cases, which is the page it would point to', () => {
    renderWithRouter(
      <CaseSent variant="page" state="limit" limitLine={WAITING_LIMIT} link={null} />,
    )
    expect(screen.getByRole('status')).toHaveTextContent(WAITING_LIMIT)
    expect(screen.queryByRole('link', { name: 'View your cases' })).not.toBeInTheDocument()
  })

  it('carries the HR contacts on the page, where no panel is above it', () => {
    renderWithRouter(
      <CaseSent
        variant="page"
        state="limit"
        limitLine={WAITING_LIMIT}
        link={null}
        contacts={[DANA]}
      />,
    )
    expect(screen.getByRole('heading', { name: 'HR contacts' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: DANA.workEmail })).toBeInTheDocument()
  })

  it('has no contacts in the panel, which shows them already', () => {
    renderWithRouter(
      <CaseSent
        variant="panel"
        state="limit"
        limitLine={WAITING_LIMIT}
        link={null}
        contacts={[DANA]}
      />,
    )
    expect(screen.queryByRole('heading', { name: 'HR contacts' })).not.toBeInTheDocument()
  })
})

describe('CaseSent: its props', () => {
  it('needs the API’s sent line for the sent state, and its limit line for the limit', () => {
    // These lines fail to compile if the props stop being a union on `state`.
    // @ts-expect-error a sent state without its line
    const sentWithoutLine = <CaseSent variant="panel" state="sent" />
    // @ts-expect-error a limit state without the API's line
    const limitWithoutLine = <CaseSent variant="panel" state="limit" />
    expect([sentWithoutLine, limitWithoutLine]).toHaveLength(2)
  })
})
