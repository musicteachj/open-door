import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { CitationOut } from '@/api/generated'
import { apiCitations, citation } from '@/test/assistant-fixtures'
import { SourceChip, SourceChips } from './source-chip'
import * as sources from './sources'

const ca1 = citation({ marker: 1, passageId: 'CA-4.3~p1' })
const ca2 = citation({ marker: 1, passageId: 'CA-4.3~p2', offsetUtf16: 40 })
const co = citation({
  marker: 2,
  sectionId: '4.3',
  passageId: '4.3~p3',
  groupName: 'Company handbook',
  title: 'Sick leave',
})

describe('SourceChip', () => {
  it('shows the number and the label, and is named by the full source', () => {
    render(<SourceChip citation={ca1} expanded={false} onOpen={() => {}} />)
    const chip = screen.getByRole('button', {
      name: 'Source 1: Handbook CA-4.3, California addendum',
    })
    expect(chip).toHaveTextContent('1')
    expect(chip).toHaveTextContent('Handbook CA-4.3 · California addendum')
    expect(chip).toHaveAttribute('aria-expanded', 'false')
  })

  it('truncates a long label in its own element, so the name keeps all of it', () => {
    render(<SourceChip citation={ca1} expanded={false} onOpen={() => {}} />)
    const label = screen.getByText('Handbook CA-4.3 · California addendum')
    expect(label).toHaveClass('truncate')
  })

  it('is expanded when told so, and hands back its citation on click', async () => {
    const onOpen = vi.fn<(citation: CitationOut) => void>()
    render(<SourceChip citation={ca1} expanded onOpen={onOpen} />)
    const chip = screen.getByRole('button')
    expect(chip).toHaveAttribute('aria-expanded', 'true')
    await userEvent.click(chip)
    expect(onOpen).toHaveBeenCalledExactlyOnceWith(ca1)
  })
})

describe('SourceChips: the numbering work', () => {
  it('numbers the citations once, and not again when only the open passage changes', () => {
    const spy = vi.spyOn(sources, 'numberBySection')
    const citations = apiCitations()
    const { rerender } = render(<SourceChips citations={citations} onOpen={() => {}} />)
    expect(spy).toHaveBeenCalledTimes(1)
    rerender(<SourceChips citations={citations} openPassageId="CA-4.3~p2" onOpen={() => {}} />)
    rerender(<SourceChips citations={citations} openPassageId="4.3~p3" onOpen={() => {}} />)
    expect(spy).toHaveBeenCalledTimes(1)
    spy.mockRestore()
  })

  it('still shows the same chips', () => {
    render(<SourceChips citations={apiCitations()} onOpen={() => {}} />)
    expect(screen.getAllByRole('button')).toHaveLength(2)
  })
})

describe('SourceChips: citations as the API sends them', () => {
  it('shows one chip per section, numbered by section, each opening the first passage cited', async () => {
    const onOpen = vi.fn<(citation: CitationOut) => void>()
    render(<SourceChips citations={apiCitations()} onOpen={onOpen} />)
    const chips = within(screen.getByRole('list', { name: 'Sources' })).getAllByRole('button')
    expect(chips.map((chip) => chip.getAttribute('aria-label'))).toEqual([
      'Source 1: Handbook CA-4.3, California addendum',
      'Source 2: Handbook §4.3, Company handbook',
    ])
    await userEvent.click(chips[0]!)
    expect(onOpen).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ passageId: 'CA-4.3~p1', marker: 1 }),
    )
  })

  it('marks a chip expanded when any passage of its section is open, not only the first', () => {
    render(<SourceChips citations={apiCitations()} openPassageId="CA-4.3~p2" onOpen={() => {}} />)
    expect(screen.getByRole('button', { name: /^Source 1/ })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    expect(screen.getByRole('button', { name: /^Source 2/ })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
  })

  it('hands back the open passage of its section when an open chip is pressed, so the caller can close it', async () => {
    const onOpen = vi.fn<(citation: CitationOut) => void>()
    render(<SourceChips citations={apiCitations()} openPassageId="CA-4.3~p2" onOpen={onOpen} />)
    await userEvent.click(screen.getByRole('button', { name: /^Source 1/ }))
    expect(onOpen).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ passageId: 'CA-4.3~p2', marker: 1 }),
    )
  })

  it('hands back its own first passage when it is not open, even if another section is', async () => {
    const onOpen = vi.fn<(citation: CitationOut) => void>()
    render(<SourceChips citations={apiCitations()} openPassageId="CA-4.3~p2" onOpen={onOpen} />)
    await userEvent.click(screen.getByRole('button', { name: /^Source 2/ }))
    expect(onOpen).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ passageId: '4.3~p3', marker: 2 }),
    )
  })

  it('marks a chip expanded when the open passage is the one it opens', () => {
    render(<SourceChips citations={apiCitations()} openPassageId="4.3~p3" onOpen={() => {}} />)
    expect(screen.getByRole('button', { name: /^Source 2/ })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
  })
})

describe('SourceChips', () => {
  it('is a "Sources" list with one chip per distinct section, in marker order', () => {
    render(<SourceChips citations={[ca1, ca2, co, ca1]} onOpen={() => {}} />)
    expect(screen.getByText('Sources')).toBeInTheDocument()
    const items = within(screen.getByRole('list', { name: 'Sources' })).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('Handbook CA-4.3 · California addendum')
    expect(items[1]).toHaveTextContent('Handbook §4.3 · Company handbook')
  })

  it('opens the first passage cited from the section', async () => {
    const onOpen = vi.fn<(citation: CitationOut) => void>()
    render(<SourceChips citations={[ca1, ca2, co]} onOpen={onOpen} />)
    await userEvent.click(screen.getByRole('button', { name: /^Source 1/ }))
    expect(onOpen).toHaveBeenCalledExactlyOnceWith(ca1)
  })

  it('marks the chip whose passage is open as expanded', () => {
    render(<SourceChips citations={[ca1, co]} openPassageId="4.3~p3" onOpen={() => {}} />)
    expect(screen.getByRole('button', { name: /^Source 1/ })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
    expect(screen.getByRole('button', { name: /^Source 2/ })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
  })

  it('renders nothing without citations', () => {
    const { container } = render(<SourceChips citations={[]} onOpen={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })
})
