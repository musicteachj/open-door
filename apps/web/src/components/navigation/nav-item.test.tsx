import { screen } from '@testing-library/react'
import { MessageCircle } from 'lucide-react'
import { describe, expect, it } from 'vitest'
import { renderWithRouter } from '@/test/render-with-router'
import { NavItem } from './nav-item'

describe('NavItem', () => {
  it('is a link to its page', () => {
    renderWithRouter(<NavItem icon={MessageCircle} label="Ask" to="/ask" />)
    expect(screen.getByRole('link', { name: 'Ask' })).toHaveAttribute('href', '/ask')
  })

  it('marks the current page with aria-current and the tint, in semibold', () => {
    renderWithRouter(<NavItem icon={MessageCircle} label="Ask" to="/ask" current />)
    const link = screen.getByRole('link', { name: 'Ask' })
    expect(link).toHaveAttribute('aria-current', 'page')
    expect(link).toHaveClass('bg-primary-tint', 'font-semibold')
  })

  it('is current by itself when the route matches its page', () => {
    renderWithRouter(<NavItem icon={MessageCircle} label="Ask" to="/ask" />, { at: '/ask' })
    expect(screen.getByRole('link', { name: 'Ask' })).toHaveAttribute('aria-current', 'page')
  })

  it('stays current on a page below its own, such as a person in the directory', () => {
    renderWithRouter(<NavItem icon={MessageCircle} label="Directory" to="/directory" />, {
      at: '/directory/abc',
    })
    expect(screen.getByRole('link', { name: 'Directory' })).toHaveAttribute('aria-current', 'page')
  })

  it('has no aria-current, and no tint, when it is not the current page', () => {
    renderWithRouter(<NavItem icon={MessageCircle} label="Ask" to="/ask" />, { at: '/directory' })
    const link = screen.getByRole('link', { name: 'Ask' })
    expect(link).not.toHaveAttribute('aria-current')
    expect(link.className).not.toMatch(/tint/)
    expect(link).not.toHaveClass('font-semibold')
  })

  it('hovers to neutral-hover, never the tint', () => {
    renderWithRouter(<NavItem icon={MessageCircle} label="Ask" to="/ask" />, { at: '/directory' })
    const link = screen.getByRole('link', { name: 'Ask' })
    expect(link).toHaveClass('hover:bg-neutral-hover')
    expect(link.className).not.toMatch(/hover:\S*tint/)
  })

  it('names the count, and shows it as a badge', () => {
    renderWithRouter(<NavItem icon={MessageCircle} label="Approvals" to="/approvals" count={1} />)
    const link = screen.getByRole('link', { name: 'Approvals, 1 waiting' })
    const badge = link.querySelector('[data-slot="nav-count"]')!
    expect(badge).toHaveTextContent('1')
    expect(badge).toHaveAttribute('aria-hidden', 'true')
    expect(badge).toHaveClass('bg-primary', 'text-on-primary', 'rounded-full')
  })

  it('can name the count with another word and show that word in the badge ("3 new")', () => {
    renderWithRouter(
      <NavItem
        icon={MessageCircle}
        label="Cases"
        to="/cases"
        count={3}
        countWord="new"
        wordInBadge
      />,
    )
    const link = screen.getByRole('link', { name: 'Cases, 3 new' })
    expect(link.querySelector('[data-slot="nav-count"]')).toHaveTextContent('3 new')
  })

  it('shows no badge for no count, or a count of zero', () => {
    renderWithRouter(<NavItem icon={MessageCircle} label="Approvals" to="/approvals" count={0} />)
    const link = screen.getByRole('link', { name: 'Approvals' })
    expect(link.querySelector('[data-slot="nav-count"]')).toBeNull()
  })

  it('hides its icon from screen readers', () => {
    renderWithRouter(<NavItem icon={MessageCircle} label="Ask" to="/ask" />)
    expect(screen.getByRole('link').querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
  })
})
