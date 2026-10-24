import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HOLIDAY_RULE, PTO_RULE, SICK_RULE } from '@/app/gallery/fixtures/timeoff'
import { renderWithRouter } from '@/test/render-with-router'
import { RuleChip, RuleChips } from './rule-chip'

describe('RuleChip', () => {
  it('is a link to the rule’s handbook section, named for its source', () => {
    renderWithRouter(<RuleChip rule={PTO_RULE} />)
    const chip = screen.getByRole('link', { name: 'Source: Handbook §4.1, Paid time off' })
    expect(chip).toHaveAttribute('href', '/handbook/4.1')
    expect(chip).toHaveTextContent('Handbook §4.1 · Paid time off')
  })

  it('puts no section sign before an addendum id', () => {
    renderWithRouter(<RuleChip rule={SICK_RULE} />)
    expect(screen.getByRole('link')).toHaveTextContent('Handbook CA-4.3 · Sick leave')
    expect(screen.getByRole('link')).toHaveAccessibleName('Source: Handbook CA-4.3, Sick leave')
  })

  it('is a 24 px chip with a strong border, caption text, and a 13 px book icon', () => {
    renderWithRouter(<RuleChip rule={PTO_RULE} />)
    const chip = screen.getByRole('link')
    expect(chip).toHaveClass('h-6', 'rounded-xs', 'border-border-strong', 'text-caption')
    expect(chip.className).toContain('hover:bg-surface-hover')
    expect(chip.className).toContain('hover:border-border-strong-hover')
    expect(chip.className).toContain('focus-visible:outline-focus-ring')
    const icon = chip.querySelector('svg')
    expect(icon).toHaveAttribute('aria-hidden', 'true')
    expect(icon).toHaveAttribute('width', '13')
  })

  it('truncates a long label and keeps it inside the row', () => {
    renderWithRouter(
      <RuleChip rule={{ ...PTO_RULE, title: 'A very long section title '.repeat(6) }} />,
    )
    const chip = screen.getByRole('link')
    expect(chip).toHaveClass('max-w-full', 'min-w-0')
    expect(chip.querySelector('span')).toHaveClass('truncate')
    expect(chip.getAttribute('aria-label')).toContain('A very long section title')
  })
})

describe('RuleChips', () => {
  it('leads with Sources and lists a chip for each rule, wrapping', () => {
    renderWithRouter(<RuleChips rules={[PTO_RULE, HOLIDAY_RULE]} />)
    expect(screen.getByText('Sources')).toBeInTheDocument()
    const list = screen.getByRole('list', { name: 'Sources' })
    expect(within(list).getAllByRole('link')).toHaveLength(2)
    expect(list).toHaveClass('flex-wrap')
  })

  it('renders nothing for no rules', () => {
    const { container } = renderWithRouter(<RuleChips rules={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
