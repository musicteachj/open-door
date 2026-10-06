import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Button } from './button'

describe('Button', () => {
  it('is a primary button at 40 px with a 10 px radius by default', () => {
    render(<Button>Ask</Button>)
    const button = screen.getByRole('button', { name: 'Ask' })
    expect(button).toHaveAttribute('type', 'button')
    expect(button).toHaveClass('bg-primary', 'text-on-primary', 'h-control', 'rounded-md')
    expect(button).toHaveClass(
      'text-ui',
      'font-semibold',
      'transition-[color,background-color,border-color]',
    )
  })

  it.each([
    ['secondary', ['bg-surface-raised', 'border-border-strong']],
    ['ghost', ['bg-transparent', 'text-primary']],
    ['destructive', ['bg-danger', 'text-on-danger']],
  ] as const)('has the %s variant', (variant, classes) => {
    render(<Button variant={variant}>Go</Button>)
    expect(screen.getByRole('button')).toHaveClass(...classes)
  })

  it('has a 32 px size with an 8 px radius', () => {
    render(<Button size="sm">Retry</Button>)
    const button = screen.getByRole('button')
    expect(button).toHaveClass('h-control-sm', 'rounded-sm', 'text-small', 'font-semibold')
    expect(button).not.toHaveClass('h-control', 'rounded-md')
  })

  it('draws the disabled colors and blocks clicks when disabled', async () => {
    const onClick = vi.fn<() => void>()
    render(
      <Button disabled onClick={onClick}>
        Send
      </Button>,
    )
    const button = screen.getByRole('button')
    expect(button).toBeDisabled()
    expect(button).toHaveClass('disabled:bg-disabled-bg', 'disabled:text-disabled-fg')
    await userEvent.setup().click(button)
    expect(onClick).not.toHaveBeenCalled()
  })

  describe('loading', () => {
    it('shows a spinner before the label, keeps the label, and sets aria-busy', () => {
      render(<Button loading>Save</Button>)
      const button = screen.getByRole('button', { name: 'Save' })
      expect(button).toHaveAttribute('aria-busy', 'true')
      const spinner = button.querySelector('[data-slot="button-spinner"]')
      expect(spinner).toBeInTheDocument()
      expect(spinner).toHaveAttribute('aria-hidden', 'true')
      expect(spinner).toHaveClass('animate-spin')
      // The spinner comes first, then the label.
      expect(button.firstElementChild).toBe(spinner)
      expect(button).toHaveTextContent('Save')
    })

    it('does not set aria-busy when idle', () => {
      render(<Button>Save</Button>)
      expect(screen.getByRole('button')).not.toHaveAttribute('aria-busy')
    })

    it('ignores clicks, by mouse and by keyboard', async () => {
      const onClick = vi.fn<() => void>()
      const user = userEvent.setup()
      render(
        <Button loading onClick={onClick}>
          Save
        </Button>,
      )
      const button = screen.getByRole('button')
      await user.click(button)
      button.focus()
      await user.keyboard('{Enter}')
      await user.keyboard(' ')
      expect(onClick).not.toHaveBeenCalled()
    })

    it('stays focusable, because disabled would drop a keyboard user’s focus', async () => {
      const user = userEvent.setup()
      render(<Button loading>Save</Button>)
      const button = screen.getByRole('button')
      expect(button).not.toBeDisabled()
      await user.tab()
      expect(button).toHaveFocus()
    })

    it('still clicks once loading ends', async () => {
      const onClick = vi.fn<() => void>()
      const { rerender } = render(
        <Button loading onClick={onClick}>
          Save
        </Button>,
      )
      rerender(<Button onClick={onClick}>Save</Button>)
      await userEvent.setup().click(screen.getByRole('button'))
      expect(onClick).toHaveBeenCalledTimes(1)
    })
  })
})
