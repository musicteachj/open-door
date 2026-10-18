import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DANA } from '@/test/assistant-fixtures'
import { HrContacts } from './hr-contacts'

const rows = () =>
  within(screen.getByRole('list', { name: 'HR contacts' })).getAllByRole('listitem')

describe('HrContacts', () => {
  it('has the heading and the line saying a person reads these', () => {
    render(<HrContacts contacts={[DANA]} />)
    expect(screen.getByRole('heading', { name: 'HR contacts' })).toBeInTheDocument()
    expect(
      screen.getByText('A person on the HR team reads and answers these, not the AI.'),
    ).toBeInTheDocument()
  })

  it('shows each person with initials, name, title and location, and a mailto link', () => {
    render(<HrContacts contacts={[DANA]} />)
    const [dana] = rows()
    expect(dana).toHaveTextContent('DW')
    expect(dana).toHaveTextContent('Dana Whitfield')
    expect(dana).toHaveTextContent('HR Business Partner · Denver HQ')
    expect(
      within(dana!).getByRole('link', { name: 'dana.whitfield@juniperrow.example' }),
    ).toHaveAttribute('href', 'mailto:dana.whitfield@juniperrow.example')
  })

  it('lets an address break after the @ and nowhere else, and keeps its name and address', () => {
    render(<HrContacts contacts={[DANA]} />)
    const link = within(rows()[0]!).getByRole('link', {
      name: 'dana.whitfield@juniperrow.example',
    })
    const breaks = link.querySelectorAll('wbr')
    expect(breaks).toHaveLength(1)
    expect(breaks[0]!.previousSibling?.textContent).toBe('dana.whitfield@')
    expect(breaks[0]!.nextSibling?.textContent).toBe('juniperrow.example')
    expect(link.textContent).toBe('dana.whitfield@juniperrow.example')
    expect(link).toHaveAttribute('href', 'mailto:dana.whitfield@juniperrow.example')
    // A part too long to fit on its own may still break anywhere, as the last resort.
    expect(link).toHaveClass('[overflow-wrap:anywhere]')
  })

  it('breaks the shared inbox address after the @ too', () => {
    render(<HrContacts contacts={[]} />)
    const link = within(rows()[0]!).getByRole('link', { name: 'hr@juniperrow.example' })
    expect(link.querySelectorAll('wbr')).toHaveLength(1)
    expect(link.textContent).toBe('hr@juniperrow.example')
  })

  it('hides the initials from a screen reader, since the name is beside them', () => {
    render(<HrContacts contacts={[DANA]} />)
    expect(rows()[0]!.querySelector('[data-slot="avatar"]')).toHaveAttribute('aria-hidden', 'true')
  })

  it('leaves out the title and location when the API does not send them', () => {
    render(<HrContacts contacts={[{ name: 'Dana Whitfield', workEmail: DANA.workEmail }]} />)
    expect(rows()[0]).not.toHaveTextContent('·')
    expect(rows()[0]).toHaveTextContent(/^DWDana Whitfielddana\.whitfield@juniperrow\.example$/)
  })

  it('shows just the one that is given when only one of title and location is', () => {
    render(
      <HrContacts
        contacts={[
          { name: 'Dana Whitfield', workEmail: DANA.workEmail, jobTitle: 'HR Business Partner' },
          { name: 'Sam Lee', workEmail: 'sam.lee@juniperrow.example', locationName: 'Denver HQ' },
        ]}
      />,
    )
    expect(rows()[0]).toHaveTextContent('HR Business Partner')
    expect(rows()[0]).not.toHaveTextContent('·')
    expect(rows()[1]).toHaveTextContent('Denver HQ')
    expect(rows()[1]).not.toHaveTextContent('·')
  })

  it('shows the people icon, not an empty circle, for a name with no letters', () => {
    render(<HrContacts contacts={[{ name: '   ', workEmail: 'blank@juniperrow.example' }]} />)
    const blank = rows()[0]!
    expect(blank.querySelector('[data-slot="avatar-fallback"]')).not.toBeEmptyDOMElement()
    expect(blank.querySelector('[data-slot="avatar-fallback"] svg')).not.toBeNull()
  })

  it('lists two contacts that share an address, with no duplicate key warning', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <HrContacts
        contacts={[
          { name: 'Dana Whitfield', workEmail: 'hr-team@juniperrow.example' },
          { name: 'Sam Lee', workEmail: 'hr-team@juniperrow.example' },
        ]}
      />,
    )
    expect(rows()).toHaveLength(3)
    expect(rows()[0]).toHaveTextContent('Dana Whitfield')
    expect(rows()[1]).toHaveTextContent('Sam Lee')
    expect(error).not.toHaveBeenCalled()
    error.mockRestore()
  })

  it('ends with the shared HR inbox, after every person', () => {
    render(
      <HrContacts
        contacts={[DANA, { name: 'Sam Lee', workEmail: 'sam.lee@juniperrow.example' }]}
      />,
    )
    const all = rows()
    expect(all).toHaveLength(3)
    const inbox = all[2]!
    expect(inbox).toHaveTextContent('HR team')
    expect(inbox).toHaveTextContent('Shared inbox')
    expect(within(inbox).getByRole('link', { name: 'hr@juniperrow.example' })).toHaveAttribute(
      'href',
      'mailto:hr@juniperrow.example',
    )
    expect(inbox.querySelector('svg')).not.toBeNull()
  })

  it('still lists the inbox when the directory has no HR person', () => {
    render(<HrContacts contacts={[]} />)
    expect(rows()).toHaveLength(1)
    expect(rows()[0]).toHaveTextContent('hr@juniperrow.example')
  })

  it('cannot add a subject or a recipient to a mailto link through an odd address', () => {
    render(
      <HrContacts
        contacts={[{ name: 'Eve', workEmail: 'eve@juniperrow.example?bcc=x@evil.example' }]}
      />,
    )
    const href = within(rows()[0]!).getByRole('link').getAttribute('href')!
    expect(href).not.toContain('?')
    expect(href.startsWith('mailto:eve@juniperrow.example')).toBe(true)
  })

  it('stacks a row at narrow widths and puts the email beside the name from the small breakpoint', () => {
    render(<HrContacts contacts={[DANA]} />)
    expect(rows()[0]).toHaveClass(
      'grid-cols-[auto_minmax(0,1fr)]',
      'sm:grid-cols-[auto_minmax(0,1fr)_auto]',
    )
  })

  it('can be the standalone bordered card under a not-found answer', () => {
    const { rerender } = render(<HrContacts contacts={[DANA]} />)
    const root = document.querySelector('[data-slot="hr-contacts"]')!
    expect(root).not.toHaveClass('border')
    rerender(<HrContacts contacts={[DANA]} variant="card" />)
    expect(document.querySelector('[data-slot="hr-contacts"]')).toHaveClass('border', 'rounded-lg')
  })
})
