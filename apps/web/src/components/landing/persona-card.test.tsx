import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PersonaCard } from './persona-card'

const priya = {
  name: 'Priya Raman',
  role: 'Visual Merchandiser',
  location: 'Oakland store',
  prompt: 'Ask about California sick leave and book a day off.',
}

describe('PersonaCard', () => {
  it('is one button, named by what it shows', () => {
    render(<PersonaCard {...priya} onSelect={() => {}} />)
    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(1)
    // The name is what the card shows, in order (WCAG 2.5.3). jsdom doesn't lay out the card, so
    // the pieces may run together here; a browser spaces them.
    expect(buttons[0]).toHaveAccessibleName(
      'Priya Raman, Visual Merchandiser, Oakland store. Ask about California sick leave and book a day off. Start as Priya',
    )
  })

  it('shows the initials, role, location, prompt, and "Start as" the first name', () => {
    render(<PersonaCard {...priya} onSelect={() => {}} />)
    const button = screen.getByRole('button')
    for (const text of [
      'PR',
      'Priya Raman',
      'Visual Merchandiser',
      'Oakland store',
      priya.prompt,
    ]) {
      expect(button).toHaveTextContent(text)
    }
    expect(button).toHaveTextContent('Start as Priya')
  })

  it('takes a start label and initials from props', () => {
    render(<PersonaCard {...priya} initials="PX" startLabel="Begin" onSelect={() => {}} />)
    expect(screen.getByRole('button')).toHaveTextContent('PX')
    expect(screen.getByRole('button')).toHaveTextContent('Begin')
  })

  it('calls onSelect on a click', async () => {
    const onSelect = vi.fn<() => void>()
    render(<PersonaCard {...priya} onSelect={onSelect} />)
    await userEvent.click(screen.getByRole('button'))
    expect(onSelect).toHaveBeenCalledTimes(1)
  })

  it('is not busy when idle', () => {
    render(<PersonaCard {...priya} onSelect={() => {}} />)
    expect(screen.getByRole('button')).not.toHaveAttribute('aria-busy', 'true')
  })

  describe('starting', () => {
    it('shows a spinner and "Setting up Juniper Row…", and is busy', () => {
      render(<PersonaCard {...priya} status="starting" onSelect={() => {}} />)
      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('aria-busy', 'true')
      expect(button).toHaveTextContent('Setting up Juniper Row…')
      expect(button).not.toHaveTextContent('Start as Priya')
      expect(button.querySelector('svg.animate-spin')).not.toBeNull()
    })

    it('stays enabled, so keyboard focus is not dropped', () => {
      render(<PersonaCard {...priya} status="starting" onSelect={() => {}} />)
      expect(screen.getByRole('button')).toBeEnabled()
    })

    it('keeps its primary border on hover, so it carries no hover-border class', () => {
      const { rerender } = render(<PersonaCard {...priya} onSelect={() => {}} />)
      expect(screen.getByRole('button').className).toContain('hover:border-input-border-hover')
      rerender(<PersonaCard {...priya} status="starting" onSelect={() => {}} />)
      expect(screen.getByRole('button').className).not.toContain('hover:border-input-border-hover')
    })

    it('does not start twice on another click', async () => {
      const onSelect = vi.fn<() => void>()
      render(<PersonaCard {...priya} status="starting" onSelect={onSelect} />)
      await userEvent.click(screen.getByRole('button'))
      await userEvent.type(screen.getByRole('button'), '{Enter} ')
      expect(onSelect).not.toHaveBeenCalled()
    })

    it('announces itself politely', () => {
      const { rerender } = render(<PersonaCard {...priya} onSelect={() => {}} />)
      const live = screen.getByRole('status')
      expect(live).toBeEmptyDOMElement()
      rerender(<PersonaCard {...priya} status="starting" onSelect={() => {}} />)
      expect(screen.getByRole('status')).toHaveTextContent('Setting up Juniper Row…')
    })

    it('takes its text from a prop', () => {
      render(
        <PersonaCard {...priya} status="starting" startingLabel="Hold on…" onSelect={() => {}} />,
      )
      expect(screen.getByRole('button')).toHaveTextContent('Hold on…')
    })
  })

  describe('disabled', () => {
    it('is its own state: the button is disabled and ignores a click', async () => {
      const onSelect = vi.fn<() => void>()
      render(<PersonaCard {...priya} disabled onSelect={onSelect} />)
      const button = screen.getByRole('button')
      expect(button).toBeDisabled()
      await userEvent.click(button)
      expect(onSelect).not.toHaveBeenCalled()
    })

    it('is not busy', () => {
      render(<PersonaCard {...priya} disabled onSelect={() => {}} />)
      expect(screen.getByRole('button')).not.toHaveAttribute('aria-busy', 'true')
    })
  })
})
