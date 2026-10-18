import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { UserMessage } from './user-message'

describe('UserMessage', () => {
  it('shows the question, led by a hidden "You asked" for a screen reader', () => {
    render(<UserMessage text="How many sick days do I get?" />)
    const message = screen.getByText('How many sick days do I get?')
    expect(message).toHaveTextContent('You asked: How many sick days do I get?')
    expect(message.querySelector('.sr-only')).toHaveTextContent('You asked:')
  })

  it('sits on the right, on surface-hover, at most 85% wide', () => {
    render(<UserMessage text="Hello" />)
    const message = screen.getByText('Hello')
    expect(message).toHaveClass('self-end', 'bg-surface-hover', 'max-w-[85%]')
  })

  it('shows HTML as the characters it was typed with', () => {
    const { container } = render(<UserMessage text="a <b>bold</b> <script>x</script>" />)
    expect(container.querySelector('b, script')).toBeNull()
    expect(container).toHaveTextContent('a <b>bold</b> <script>x</script>')
  })

  it('never renders Markdown', () => {
    const { container } = render(<UserMessage text="**not bold** and [a link](/handbook/4.3)" />)
    expect(container.querySelector('strong, a')).toBeNull()
    expect(container).toHaveTextContent('**not bold** and [a link](/handbook/4.3)')
  })

  it('keeps line breaks and runs of spaces as typed', () => {
    render(<UserMessage text={'first\nsecond  line'} />)
    const message = screen.getByText(/first/)
    expect(message).toHaveClass('whitespace-pre-wrap')
    expect(message.textContent).toContain('first\nsecond  line')
  })

  it('breaks a long unbroken word instead of scrolling sideways', () => {
    render(<UserMessage text={'x'.repeat(300)} />)
    expect(screen.getByText('x'.repeat(300))).toHaveClass('break-words')
  })
})
