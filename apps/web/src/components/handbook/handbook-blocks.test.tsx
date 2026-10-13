import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { ListPassage, SectionDetail } from '@/api/generated'
import { paragraph } from '@/test/handbook-fixtures'
import { renderWithRouter } from '@/test/render-with-router'
import { HandbookBlocks } from './handbook-blocks'

type Blocks = SectionDetail['blocks']

const plain = (text: string) => ({ text, bold: false, italic: false, linkSectionId: null })

const bullets: ListPassage = {
  type: 'passage',
  id: 'p3',
  kind: 'list',
  ordered: false,
  items: [[plain('Accrual starts on day one.')], [plain('Carryover is capped.')]],
}
const steps: ListPassage = { ...bullets, id: 'p4', ordered: true }

const blocks: Blocks = [
  { type: 'heading', level: 2, text: 'How it accrues' },
  paragraph('p1', 'Employees earn sick leave as they work.'),
  { type: 'heading', level: 3, text: 'Carryover' },
  bullets,
  steps,
]

describe('HandbookBlocks', () => {
  it('renders headings at their level, paragraphs, and both list kinds as elements', () => {
    renderWithRouter(<HandbookBlocks blocks={blocks} />)
    expect(screen.getByRole('heading', { level: 2, name: 'How it accrues' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3, name: 'Carryover' })).toBeInTheDocument()
    expect(screen.getByText('Employees earn sick leave as they work.').tagName).toBe('P')
    const lists = screen.getAllByRole('list')
    expect(lists.map((l) => l.tagName)).toEqual(['UL', 'OL'])
    expect(within(lists[0]).getAllByRole('listitem')).toHaveLength(2)
  })

  it('renders bold, italic, and a handbook link as a router link', () => {
    renderWithRouter(
      <HandbookBlocks
        blocks={[
          {
            type: 'passage',
            id: 'p1',
            kind: 'paragraph',
            inlines: [
              { text: 'Read ', bold: false, italic: false, linkSectionId: null },
              { text: 'this', bold: true, italic: false, linkSectionId: null },
              { text: 'that', bold: false, italic: true, linkSectionId: null },
              { text: 'CA-4.3', bold: false, italic: false, linkSectionId: 'CA-4.3' },
            ],
          },
        ]}
      />,
    )
    expect(screen.getByText('this').tagName).toBe('STRONG')
    expect(screen.getByText('that').tagName).toBe('EM')
    expect(screen.getByRole('link', { name: 'CA-4.3' })).toHaveAttribute('href', '/handbook/CA-4.3')
  })

  it('encodes a section id in an inline link', () => {
    renderWithRouter(
      <HandbookBlocks
        blocks={[
          {
            type: 'passage',
            id: 'p1',
            kind: 'paragraph',
            inlines: [{ text: 'odd', bold: false, italic: false, linkSectionId: 'a/b' }],
          },
        ]}
      />,
    )
    const link = screen.getByRole('link', { name: 'odd' })
    expect(link).toHaveAttribute('href', '/handbook/a%2Fb')
  })

  it('gives every passage its id, and escapes markup in the text', () => {
    const { container } = renderWithRouter(
      <HandbookBlocks blocks={[paragraph('p1', '<b>not bold</b>'), bullets]} />,
    )
    expect(container.querySelector('[data-passage-id="p1"]')).not.toBeNull()
    expect(container.querySelector('[data-passage-id="p3"]')).not.toBeNull()
    expect(container.querySelector('b')).toBeNull()
    expect(screen.getByText('<b>not bold</b>')).toBeInTheDocument()
  })

  it('marks the cited passage as the "Cited passage" region, with Clear highlight', async () => {
    const onClear = vi.fn<() => void>()
    const { user } = renderWithRouter(
      <HandbookBlocks blocks={blocks} citedPassageId="p1" onClearCitation={onClear} />,
    )
    const region = screen.getByRole('region', { name: 'Cited passage' })
    expect(region).toHaveTextContent('Employees earn sick leave as they work.')
    expect(region).toHaveAttribute('data-passage-id', 'p1')
    // Only the one passage is cited.
    expect(screen.getAllByRole('region')).toHaveLength(1)
    // Inside the block's own gap column, the region adds no bottom margin of its own.
    expect(region).not.toHaveClass('mb-4')
    await user.click(within(region).getByRole('button', { name: 'Clear highlight' }))
    expect(onClear).toHaveBeenCalledTimes(1)
  })

  it('scrolls to the cited passage and focuses it when asked', () => {
    const scroll = vi.fn<() => void>()
    window.HTMLElement.prototype.scrollIntoView = scroll
    renderWithRouter(<HandbookBlocks blocks={blocks} citedPassageId="p3" focusCited />)
    expect(scroll).toHaveBeenCalled()
    expect(screen.getByRole('region', { name: 'Cited passage' })).toHaveFocus()
  })

  it('scrolls and focuses again when another section arrives with the same passage id', () => {
    // Passage ids restart in every section, so a citation can move from 4.3's p1 to CA-4.3's p1.
    const scroll = vi.fn<() => void>()
    window.HTMLElement.prototype.scrollIntoView = scroll
    const other: Blocks = [paragraph('p1', 'California adds its own rules.')]
    const view = (b: Blocks) => (
      <MemoryRouter>
        <HandbookBlocks blocks={b} citedPassageId="p1" focusCited />
        <button type="button">Elsewhere</button>
      </MemoryRouter>
    )
    const { rerender } = render(view(blocks))
    screen.getByRole('button', { name: 'Elsewhere' }).focus()
    scroll.mockClear()
    rerender(view(other))
    expect(scroll).toHaveBeenCalled()
    expect(screen.getByRole('region', { name: 'Cited passage' })).toHaveFocus()
  })

  it('keeps focus on the passage after Clear highlight removes the region', async () => {
    function Host() {
      const [cited, setCited] = useState<string | undefined>('p1')
      return (
        <HandbookBlocks
          blocks={blocks}
          citedPassageId={cited}
          onClearCitation={() => setCited(undefined)}
        />
      )
    }
    const { user } = renderWithRouter(<Host />)
    await user.click(screen.getByRole('button', { name: 'Clear highlight' }))
    expect(screen.queryByRole('region', { name: 'Cited passage' })).not.toBeInTheDocument()
    expect(screen.getByText('Employees earn sick leave as they work.')).toHaveFocus()
  })

  it('lets a new citation take focus after an earlier one was cleared', async () => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn<() => void>()
    function Host() {
      const [cited, setCited] = useState<string | undefined>('p1')
      return (
        <>
          <HandbookBlocks
            blocks={blocks}
            citedPassageId={cited}
            onClearCitation={() => setCited(undefined)}
            focusCited
          />
          <button type="button" onClick={() => setCited('p3')}>
            Cite p3
          </button>
        </>
      )
    }
    const { user } = renderWithRouter(<Host />)
    await user.click(screen.getByRole('button', { name: 'Clear highlight' }))
    await user.click(screen.getByRole('button', { name: 'Cite p3' }))
    const region = screen.getByRole('region', { name: 'Cited passage' })
    expect(region).toHaveAttribute('data-passage-id', 'p3')
    expect(region).toHaveFocus()
  })

  it('does not move focus into the next section after a citation was cleared', async () => {
    const next: Blocks = [paragraph('p1', 'California adds its own rules.')]
    function Host() {
      const [cited, setCited] = useState<string | undefined>('p1')
      const [current, setCurrent] = useState<Blocks>(blocks)
      return (
        <>
          <HandbookBlocks
            blocks={current}
            citedPassageId={cited}
            onClearCitation={() => setCited(undefined)}
          />
          <button type="button" onClick={() => setCurrent(next)}>
            Next section
          </button>
        </>
      )
    }
    const { user } = renderWithRouter(<Host />)
    await user.click(screen.getByRole('button', { name: 'Clear highlight' }))
    await user.click(screen.getByRole('button', { name: 'Next section' }))
    expect(screen.getByRole('button', { name: 'Next section' })).toHaveFocus()
  })

  it('can cite a list passage', () => {
    renderWithRouter(<HandbookBlocks blocks={blocks} citedPassageId="p3" />)
    const region = screen.getByRole('region', { name: 'Cited passage' })
    expect(within(region).getAllByRole('listitem')).toHaveLength(2)
  })

  it('ignores a cited id that matches no passage', () => {
    renderWithRouter(<HandbookBlocks blocks={blocks} citedPassageId="nope" focusCited />)
    expect(screen.queryByRole('region')).not.toBeInTheDocument()
  })
})
