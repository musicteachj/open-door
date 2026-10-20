import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import type { CitationOut } from '@/api/generated'
import { citation } from '@/test/assistant-fixtures'
import { Answer } from './answer'
import { CitationMarker } from './citation-marker'

const NAME = 'Source 1: Handbook CA-4.3, California addendum'

describe('CitationMarker', () => {
  it('is a button showing the marker number, named by its source', () => {
    render(<CitationMarker citation={citation()} expanded={false} onOpen={() => {}} />)
    const button = screen.getByRole('button', { name: NAME })
    expect(button).toHaveTextContent('1')
    expect(button).toHaveAttribute('type', 'button')
  })

  it('says whether its passage is the open one', () => {
    const { rerender } = render(
      <CitationMarker citation={citation()} expanded={false} onOpen={() => {}} />,
    )
    expect(screen.getByRole('button', { name: NAME })).toHaveAttribute('aria-expanded', 'false')
    rerender(<CitationMarker citation={citation()} expanded onOpen={() => {}} />)
    expect(screen.getByRole('button', { name: NAME })).toHaveAttribute('aria-expanded', 'true')
  })

  it('carries its passage, so focus can find it again after the page is redrawn', () => {
    render(
      <CitationMarker
        citation={citation({ passageId: 'CA-4.3~p2' })}
        expanded={false}
        onOpen={() => {}}
      />,
    )
    expect(screen.getByRole('button')).toHaveAttribute('data-passage-id', 'CA-4.3~p2')
  })

  it('hands the citation back on click', async () => {
    const onOpen = vi.fn<(citation: CitationOut) => void>()
    const cited = citation({ marker: 2, sectionId: '4.3', groupName: 'Company handbook' })
    render(<CitationMarker citation={cited} expanded={false} onOpen={onOpen} />)
    await userEvent.click(screen.getByRole('button'))
    expect(onOpen).toHaveBeenCalledExactlyOnceWith(cited)
  })

  it('has hover, active, and its own weight and style, so bold or italic text around it never changes it', () => {
    render(<CitationMarker citation={citation()} expanded onOpen={() => {}} />)
    const button = screen.getByRole('button')
    expect(button).toHaveClass('font-semibold', 'not-italic')
    expect(button).toHaveClass('hover:border-primary', 'hover:bg-primary-tint')
    expect(button).toHaveClass('aria-expanded:border-primary', 'aria-expanded:bg-primary-tint')
  })

  it('works as the answer renderer inside bold text', async () => {
    const onOpen = vi.fn<(citation: CitationOut) => void>()
    const cited = citation({ offsetUtf16: 16 })
    render(
      <MemoryRouter>
        <Answer
          text="It is **ten days off**"
          citations={[cited]}
          renderMarker={(c) => <CitationMarker citation={c} expanded={false} onOpen={onOpen} />}
        />
      </MemoryRouter>,
    )
    const button = screen.getByRole('button', { name: NAME })
    expect(button.closest('strong')).not.toBeNull()
    expect(button).toHaveClass('font-semibold', 'not-italic')
    await userEvent.click(button)
    expect(onOpen).toHaveBeenCalledExactlyOnceWith(cited)
  })
})
