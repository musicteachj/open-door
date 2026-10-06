import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { Tooltip, TooltipContent, TooltipTrigger } from './tooltip'

function Example() {
  return (
    <Tooltip>
      <TooltipTrigger>Marcus</TooltipTrigger>
      <TooltipContent>Department Lead, Apparel</TooltipContent>
    </Tooltip>
  )
}

describe('Tooltip', () => {
  it('is closed until asked', () => {
    render(<Example />)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('opens when the trigger takes keyboard focus, with no delay', async () => {
    const user = userEvent.setup()
    render(<Example />)
    await user.tab()
    expect(screen.getByRole('button', { name: 'Marcus' })).toHaveFocus()
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Department Lead, Apparel')
  })

  it('names the trigger’s description', async () => {
    const user = userEvent.setup()
    render(<Example />)
    await user.tab()
    await screen.findByRole('tooltip')
    expect(screen.getByRole('button', { name: 'Marcus' })).toHaveAccessibleDescription(
      'Department Lead, Apparel',
    )
  })

  it('opens on hover only after its delay', async () => {
    const user = userEvent.setup()
    render(<Example />)
    await user.hover(screen.getByRole('button', { name: 'Marcus' }))
    // Not yet: the delay hasn't passed.
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    expect(await screen.findByRole('tooltip', undefined, { timeout: 1500 })).toBeInTheDocument()
  })

  it('closes on Escape (WCAG 1.4.13)', async () => {
    const user = userEvent.setup()
    render(<Example />)
    await user.tab()
    await screen.findByRole('tooltip')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('tooltip')).not.toBeInTheDocument())
  })

  it('closes when focus leaves', async () => {
    const user = userEvent.setup()
    render(<Example />)
    await user.tab()
    await screen.findByRole('tooltip')
    await user.tab()
    await waitFor(() => expect(screen.queryByRole('tooltip')).not.toBeInTheDocument())
  })

  it('wears the tooltip colors, caption type, and 6 px radius', async () => {
    const user = userEvent.setup()
    render(<Example />)
    await user.tab()
    await screen.findByRole('tooltip')
    const content = document.querySelector('[data-slot="tooltip-content"]')
    expect(content).toHaveClass(
      'bg-tooltip-bg',
      'text-tooltip-fg',
      'text-caption',
      'rounded-xs',
      'shadow-md',
    )
  })
})
