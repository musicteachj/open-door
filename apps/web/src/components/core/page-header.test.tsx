import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithRouter } from '@/test/render-with-router'
import { PageHeader } from './page-header'

describe('PageHeader', () => {
  it('is an h1 with the title', () => {
    render(<PageHeader title="Directory" />)
    expect(screen.getByRole('heading', { level: 1, name: 'Directory' })).toBeInTheDocument()
  })

  it('shows the count beside the title, outside the heading', () => {
    render(<PageHeader title="Directory" count="44 of 120 people" />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveAccessibleName('Directory')
    expect(screen.getByText('44 of 120 people')).toBeInTheDocument()
  })

  it('shows a back link, and no heading, in its back form', () => {
    renderWithRouter(<PageHeader back={{ to: '/directory', label: 'Directory' }} />)
    const link = screen.getByRole('link', { name: 'Back to Directory' })
    expect(link).toHaveAttribute('href', '/directory')
    expect(link).toHaveTextContent('Directory')
    expect(screen.queryByRole('heading')).not.toBeInTheDocument()
  })

  it('has a slot on the right', () => {
    render(<PageHeader title="Directory" right={<span>Sandbox resets in 21 h</span>} />)
    expect(screen.getByText('Sandbox resets in 21 h')).toBeInTheDocument()
  })
})
