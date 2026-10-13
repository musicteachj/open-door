import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { useRef, useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { californiaSickLeave, passageView } from '@/test/handbook-fixtures'
import { renderWithRouter } from '@/test/render-with-router'
import { PassagePanel } from './passage-panel'

const base = { sectionId: 'CA-4.3', passageId: 'p2', onClose: () => {} }

describe('PassagePanel open', () => {
  it('shows the header fields, the passage, and its neighbors', () => {
    renderWithRouter(<PassagePanel {...base} state="open" view={passageView()} />)
    const panel = screen.getByRole('complementary', { name: 'Handbook passage' })
    expect(within(panel).getByText('Handbook CA-4.3 · California addendum')).toBeInTheDocument()
    expect(within(panel).getByRole('heading', { name: 'Sick leave' })).toBeInTheDocument()
    expect(within(panel).getByText('California employees')).toBeInTheDocument()
    expect(within(panel).getByText('Applies to you')).toBeInTheDocument()
    expect(within(panel).getByText('Last updated Sep 12, 2026')).toBeInTheDocument()
    const cited = within(panel).getByRole('region', { name: 'Cited passage' })
    expect(cited).toHaveTextContent('You can use sick leave for your own illness')
    expect(panel).toHaveTextContent('California employees receive 40 hours')
    expect(panel).toHaveTextContent('Tell your manager as soon as you can.')
    // The cited passage in the panel has no Clear highlight.
    expect(screen.queryByRole('button', { name: 'Clear highlight' })).not.toBeInTheDocument()
  })

  it('shows "Doesn\'t apply to you" and leaves out a missing neighbor', () => {
    renderWithRouter(
      <PassagePanel
        {...base}
        state="open"
        view={passageView({
          section: californiaSickLeave({ appliesToMe: false }),
          previous: null,
          next: null,
        })}
      />,
    )
    expect(screen.getByText("Doesn't apply to you")).toBeInTheDocument()
    expect(screen.queryByText('Tell your manager as soon as you can.')).not.toBeInTheDocument()
  })

  it('uses a section sign in the eyebrow for a company section', () => {
    renderWithRouter(
      <PassagePanel
        {...base}
        sectionId="4.3"
        state="open"
        view={passageView({
          section: {
            ...californiaSickLeave(),
            id: '4.3',
            kind: 'company',
            chapter: 4,
            groupName: 'Time off',
          },
        })}
      />,
    )
    expect(screen.getByText('Handbook §4.3 · Time off')).toBeInTheDocument()
  })

  it('links "Open in handbook" to the deep link', () => {
    renderWithRouter(<PassagePanel {...base} state="open" view={passageView()} />)
    expect(screen.getByRole('link', { name: 'Open in handbook' })).toHaveAttribute(
      'href',
      '/handbook/CA-4.3?passage=p2',
    )
  })

  it('moves focus to the title when it opens', () => {
    renderWithRouter(<PassagePanel {...base} state="open" view={passageView()} />)
    expect(screen.getByRole('heading', { name: 'Sick leave' })).toHaveFocus()
  })

  it('moves focus to the title when loading finishes, not before', () => {
    const panel = (state: 'loading' | 'open') => (
      <MemoryRouter>
        <PassagePanel {...base} state={state} view={state === 'open' ? passageView() : undefined} />
      </MemoryRouter>
    )
    const { rerender } = render(panel('loading'))
    expect(document.body).toHaveFocus()
    rerender(panel('open'))
    expect(screen.getByRole('heading', { name: 'Sick leave' })).toHaveFocus()
  })

  it('moves focus to the title again when the host swaps in another passage', () => {
    const panel = (passageId: string) => (
      <MemoryRouter>
        <PassagePanel {...base} passageId={passageId} state="open" view={passageView()} />
      </MemoryRouter>
    )
    const { rerender } = render(
      <>
        {panel('p2')}
        <button type="button">Elsewhere</button>
      </>,
    )
    screen.getByRole('button', { name: 'Elsewhere' }).focus()
    rerender(
      <>
        {panel('p3')}
        <button type="button">Elsewhere</button>
      </>,
    )
    expect(screen.getByRole('heading', { name: 'Sick leave' })).toHaveFocus()
  })

  it('has a body that scrolls inside the panel and takes focus', async () => {
    const { user } = renderWithRouter(<PassagePanel {...base} state="open" view={passageView()} />)
    const body = screen.getByLabelText('Passage text')
    expect(body).toHaveAttribute('tabindex', '0')
    expect(body).toHaveClass('overflow-auto')
    expect(screen.getByRole('heading', { name: 'Sick leave' })).toHaveFocus()
    await user.tab() // from the title, the next stop in the page is the body
    expect(body).toHaveFocus()
  })

  it('falls back to a plain eyebrow without the section', () => {
    renderWithRouter(<PassagePanel {...base} state="loading" />)
    expect(screen.getByText('Handbook CA-4.3')).toBeInTheDocument()
  })

  it("uses the host's group name for the eyebrow while loading and on error", () => {
    const { rerender } = render(
      <MemoryRouter>
        <PassagePanel {...base} state="loading" groupName="California addendum" />
      </MemoryRouter>,
    )
    expect(screen.getByText('Handbook CA-4.3 · California addendum')).toBeInTheDocument()
    rerender(
      <MemoryRouter>
        <PassagePanel {...base} state="error" groupName="California addendum" />
      </MemoryRouter>,
    )
    expect(screen.getByText('Handbook CA-4.3 · California addendum')).toBeInTheDocument()
  })

  it("uses a section sign for a company section's group name", () => {
    renderWithRouter(
      <PassagePanel {...base} sectionId="4.3" state="loading" groupName="Time off" />,
    )
    expect(screen.getByText('Handbook §4.3 · Time off')).toBeInTheDocument()
  })
})

describe('PassagePanel loading', () => {
  it('is busy, says what is loading, and keeps the footer link', () => {
    renderWithRouter(<PassagePanel {...base} state="loading" />)
    expect(screen.getByRole('complementary', { name: 'Handbook passage' })).toHaveAttribute(
      'aria-busy',
      'true',
    )
    expect(screen.getByText('Loading passage')).toBeInTheDocument()
    expect(screen.queryByRole('heading')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open in handbook' })).toBeInTheDocument()
  })
})

describe('PassagePanel error', () => {
  it('shows the inline error with Retry, as an alert', async () => {
    const onRetry = vi.fn<() => void>()
    const { user } = renderWithRouter(<PassagePanel {...base} state="error" onRetry={onRetry} />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent("Couldn't load this passage.")
    await user.click(within(alert).getByRole('button', { name: 'Retry' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('keeps "Open in handbook" in the error state', () => {
    renderWithRouter(<PassagePanel {...base} state="error" />)
    expect(screen.getByRole('link', { name: 'Open in handbook' })).toHaveAttribute(
      'href',
      '/handbook/CA-4.3?passage=p2',
    )
  })
})

describe('PassagePanel closing', () => {
  it('calls onClose from the close button and from Escape', async () => {
    const onClose = vi.fn<() => void>()
    const { user } = renderWithRouter(
      <PassagePanel {...base} onClose={onClose} state="open" view={passageView()} />,
    )
    await user.click(screen.getByRole('button', { name: 'Close passage' }))
    expect(onClose).toHaveBeenCalledTimes(1)
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('does not close on Escape typed in a field outside the panel', async () => {
    const onClose = vi.fn<() => void>()
    const { user } = renderWithRouter(
      <>
        <textarea aria-label="Message" />
        <PassagePanel {...base} onClose={onClose} state="open" view={passageView()} />
      </>,
    )
    await user.click(screen.getByLabelText('Message'))
    await user.keyboard('{Escape}')
    expect(onClose).not.toHaveBeenCalled()
  })

  it('closes on Escape with focus on the page body or inside the panel', async () => {
    const onClose = vi.fn<() => void>()
    const { user } = renderWithRouter(
      <PassagePanel {...base} onClose={onClose} state="open" view={passageView()} />,
    )
    await user.keyboard('{Escape}') // focus is on the title, inside the panel
    expect(onClose).toHaveBeenCalledTimes(1)
    ;(document.activeElement as HTMLElement).blur() // now on the body
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('does not close on Escape that ends an IME composition', () => {
    const onClose = vi.fn<() => void>()
    renderWithRouter(<PassagePanel {...base} onClose={onClose} state="open" view={passageView()} />)
    screen
      .getByRole('heading', { name: 'Sick leave' })
      .dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Escape', isComposing: true, bubbles: true }),
      )
    expect(onClose).not.toHaveBeenCalled()
  })

  it('does not close on Escape another handler already used', async () => {
    const onClose = vi.fn<() => void>()
    const { user } = renderWithRouter(
      <>
        <input aria-label="field" onKeyDown={(e) => e.preventDefault()} />
        <PassagePanel {...base} onClose={onClose} state="open" view={passageView()} />
      </>,
    )
    await user.click(screen.getByLabelText('field'))
    await user.keyboard('{Escape}')
    expect(onClose).not.toHaveBeenCalled()
  })

  it('is not modal: nothing is trapped and the page behind stays reachable', async () => {
    const { user } = renderWithRouter(
      <>
        <button type="button">Before</button>
        <PassagePanel {...base} state="open" view={passageView()} />
        <button type="button">After</button>
      </>,
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await user.tab() // title -> body
    await user.tab() // body -> Open in handbook
    await user.tab() // out of the panel, to the page behind it
    expect(screen.getByRole('button', { name: 'After' })).toHaveFocus()
  })

  it('returns focus to the citation when the host closes it', async () => {
    function Host() {
      const [open, setOpen] = useState(false)
      const citation = useRef<HTMLButtonElement>(null)
      return (
        <>
          <button ref={citation} type="button" onClick={() => setOpen(true)}>
            Sick leave, CA-4.3
          </button>
          {open && (
            <PassagePanel
              {...base}
              state="open"
              view={passageView()}
              onClose={() => {
                setOpen(false)
                citation.current?.focus()
              }}
            />
          )}
        </>
      )
    }
    const { user } = renderWithRouter(<Host />)
    const citation = screen.getByRole('button', { name: 'Sick leave, CA-4.3' })
    await user.click(citation)
    expect(screen.getByRole('heading', { name: 'Sick leave' })).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
    expect(citation).toHaveFocus()

    await user.click(citation)
    await user.click(screen.getByRole('button', { name: 'Close passage' }))
    expect(citation).toHaveFocus()
  })
})
