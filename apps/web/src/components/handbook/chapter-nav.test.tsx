import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { californiaSickLeave, sectionSummary } from '@/test/handbook-fixtures'
import { renderWithRouter } from '@/test/render-with-router'
import { ChapterNav } from './chapter-nav'

const sections = [
  sectionSummary({ id: '4.1', title: 'Vacation' }),
  sectionSummary({ id: '4.3', title: 'Sick leave' }),
  sectionSummary({ id: '4.4', title: 'Holidays' }),
]

describe('ChapterNav', () => {
  it('is a navigation landmark named by the chapter', () => {
    renderWithRouter(<ChapterNav section={sectionSummary()} sections={sections} />)
    expect(screen.getByRole('navigation', { name: 'Chapter 4 · Time off' })).toBeInTheDocument()
    expect(screen.getByText('Chapter 4 · Time off')).toBeInTheDocument()
  })

  it('names an addendum by its state', () => {
    renderWithRouter(
      <ChapterNav section={californiaSickLeave()} sections={[californiaSickLeave()]} />,
    )
    expect(screen.getByRole('navigation', { name: 'California addendum' })).toBeInTheDocument()
  })

  it('links each section, number then title', () => {
    renderWithRouter(<ChapterNav section={sectionSummary()} sections={sections} />)
    const links = screen.getAllByRole('link')
    expect(links.map((l) => l.getAttribute('href'))).toEqual([
      '/handbook/4.1',
      '/handbook/4.3',
      '/handbook/4.4',
    ])
    expect(links[1]).toHaveAccessibleName('4.3 Sick leave')
  })

  it('marks only the current section aria-current="page"', () => {
    renderWithRouter(<ChapterNav section={sectionSummary()} sections={sections} />)
    expect(screen.getByRole('link', { name: '4.3 Sick leave' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(screen.getByRole('link', { name: '4.1 Vacation' })).not.toHaveAttribute('aria-current')
    expect(screen.getByRole('link', { name: '4.4 Holidays' })).not.toHaveAttribute('aria-current')
  })

  it('has no arrow-key handling: Tab order only', async () => {
    const { user } = renderWithRouter(<ChapterNav section={sectionSummary()} sections={sections} />)
    await user.tab()
    expect(screen.getByRole('link', { name: '4.1 Vacation' })).toHaveFocus()
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('link', { name: '4.1 Vacation' })).toHaveFocus()
  })
})
