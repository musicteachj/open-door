import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { AI_DISCLOSURE } from '@/lib/disclosure'
import { Composer } from './composer'

type Props = Partial<React.ComponentProps<typeof Composer>>

// A controlled composer, as the chat store drives it.
function Harness({ initial = '', onSubmit = () => {}, ...rest }: Props & { initial?: string }) {
  const [value, setValue] = useState(initial)
  return <Composer value={value} onChange={setValue} onSubmit={onSubmit} {...rest} />
}

const box = () => screen.getByRole('textbox', { name: 'Ask Open Door' })

describe('Composer', () => {
  it('always shows the AI disclosure, and describes the box with it', () => {
    render(<Harness />)
    expect(screen.getByText(AI_DISCLOSURE)).toBeInTheDocument()
    expect(box()).toHaveAccessibleDescription(AI_DISCLOSURE)
  })

  it('has a real-ellipsis placeholder and an accessible name', () => {
    render(<Harness />)
    expect(box()).toHaveAttribute('placeholder', 'Ask about time off, pay, benefits, or policy…')
  })

  it('submits on Enter, with the text', async () => {
    const onSubmit = vi.fn<(value: string) => void>()
    render(<Harness initial="How many sick days?" onSubmit={onSubmit} />)
    await userEvent.type(box(), '{Enter}')
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith('How many sick days?')
  })

  it('adds a line on Shift+Enter instead of submitting', async () => {
    const onSubmit = vi.fn<(value: string) => void>()
    render(<Harness initial="one" onSubmit={onSubmit} />)
    await userEvent.type(box(), '{Shift>}{Enter}{/Shift}two')
    expect(onSubmit).not.toHaveBeenCalled()
    expect(box()).toHaveValue('one\ntwo')
  })

  it('does not submit on an Enter that confirms an IME composition', () => {
    const onSubmit = vi.fn<(value: string) => void>()
    render(<Harness initial="にほん" onSubmit={onSubmit} />)
    fireEvent.keyDown(box(), { key: 'Enter', isComposing: true })
    fireEvent.keyDown(box(), { key: 'Enter', keyCode: 229 })
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('focuses the box instead of submitting when Ask is pressed on an empty box', async () => {
    const onSubmit = vi.fn<(value: string) => void>()
    render(<Harness onSubmit={onSubmit} />)
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(onSubmit).not.toHaveBeenCalled()
    expect(box()).toHaveFocus()
  })

  it('treats a whitespace-only box as empty, for Ask and for Enter', async () => {
    const onSubmit = vi.fn<(value: string) => void>()
    render(<Harness initial="   " onSubmit={onSubmit} />)
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(box()).toHaveFocus()
    await userEvent.type(box(), '{Enter}')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('submits from the Ask button when there is text', async () => {
    const onSubmit = vi.fn<(value: string) => void>()
    render(<Harness initial="Book next Friday off" onSubmit={onSubmit} />)
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith('Book next Friday off')
  })

  it('keeps Ask enabled when the box is empty', () => {
    render(<Harness />)
    expect(screen.getByRole('button', { name: 'Ask' })).toBeEnabled()
  })

  it('shows an inline error with Retry, which resends the question', async () => {
    const onSubmit = vi.fn<(value: string) => void>()
    render(
      <Harness initial="How many sick days?" onSubmit={onSubmit} error="Something went wrong." />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong.')
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith('How many sick days?')
  })

  it('shows no error by default', () => {
    render(<Harness />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  describe('busy', () => {
    it('keeps Ask focusable and busy, and ignores a second send', async () => {
      const onSubmit = vi.fn<(value: string) => void>()
      render(<Harness initial="How many sick days?" onSubmit={onSubmit} busy />)
      const ask = screen.getByRole('button', { name: 'Ask' })
      expect(ask).toBeEnabled()
      expect(ask).toHaveAttribute('aria-busy', 'true')
      await userEvent.click(ask)
      await userEvent.type(box(), '{Enter}')
      expect(onSubmit).not.toHaveBeenCalled()
    })

    it('leaves the box editable, so the person can keep writing', async () => {
      render(<Harness busy />)
      await userEvent.type(box(), 'abc')
      expect(box()).toHaveValue('abc')
    })
  })
})
