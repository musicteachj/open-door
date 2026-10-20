import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { MemoryRouter } from 'react-router'
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

  it('has no second failed-send prop: sendError is the only one, and there is no Retry', () => {
    render(
      <Harness
        initial="How many sick days?"
        // @ts-expect-error `error` was deleted: a failed send is `sendError`, under the box.
        error="Something went wrong."
      />,
    )
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
    expect(screen.queryByText('Something went wrong.')).not.toBeInTheDocument()
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

  describe('streaming', () => {
    it('puts Stop in the place of Ask', () => {
      render(<Harness streaming onStop={() => {}} />)
      expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Ask' })).not.toBeInTheDocument()
    })

    it('calls onStop and moves focus back to the box', async () => {
      const onStop = vi.fn<() => void>()
      render(<Harness streaming onStop={onStop} />)
      await userEvent.click(screen.getByRole('button', { name: 'Stop' }))
      expect(onStop).toHaveBeenCalledTimes(1)
      expect(box()).toHaveFocus()
    })

    it('sends nothing on Enter, and tells the caller so it can show the send error', async () => {
      const onSubmit = vi.fn<(value: string) => void>()
      const onSubmitWhileStreaming = vi.fn<() => void>()
      render(
        <Harness
          initial="Can I carry unused days over?"
          streaming
          onStop={() => {}}
          onSubmit={onSubmit}
          onSubmitWhileStreaming={onSubmitWhileStreaming}
        />,
      )
      await userEvent.type(box(), '{Enter}')
      expect(onSubmit).not.toHaveBeenCalled()
      expect(onSubmitWhileStreaming).toHaveBeenCalledTimes(1)
      expect(box()).toHaveValue('Can I carry unused days over?')
    })

    it('still adds a line on Shift+Enter', async () => {
      const onSubmitWhileStreaming = vi.fn<() => void>()
      render(
        <Harness
          initial="one"
          streaming
          onStop={() => {}}
          onSubmitWhileStreaming={onSubmitWhileStreaming}
        />,
      )
      await userEvent.type(box(), '{Shift>}{Enter}{/Shift}two')
      expect(onSubmitWhileStreaming).not.toHaveBeenCalled()
      expect(box()).toHaveValue('one\ntwo')
    })

    it('draws Stop as its own button, never the same one that becomes Ask', () => {
      // In a browser, Stop's click can end the stream inside the click itself. If Stop and Ask were
      // one DOM node, it would turn into a submit button before the click finished, and the form
      // would submit the draft. (Testing Library batches updates until a click is over, so the
      // submit can't be seen here. The node being a different one is what prevents it.)
      const { rerender } = render(
        <Composer
          value="a draft"
          onChange={() => {}}
          onSubmit={() => {}}
          streaming
          onStop={() => {}}
        />,
      )
      const stop = screen.getByRole('button', { name: 'Stop' })
      expect(stop).toHaveAttribute('type', 'button')
      rerender(<Composer value="a draft" onChange={() => {}} onSubmit={() => {}} />)
      const ask = screen.getByRole('button', { name: 'Ask' })
      expect(ask).not.toBe(stop)
      expect(stop.isConnected).toBe(false)
    })

    it('keeps Stop while streaming even if a budget stop disables the box mid-answer', () => {
      render(
        <MemoryRouter>
          <Harness streaming onStop={() => {}} disabledReason="daily" />
        </MemoryRouter>,
      )
      expect(screen.getByRole('button', { name: 'Stop' })).toBeEnabled()
      expect(screen.queryByRole('button', { name: 'Ask' })).not.toBeInTheDocument()
      expect(box()).toBeDisabled()
    })

    it('keeps the box editable, so the next question can be written while the answer streams', async () => {
      render(<Harness streaming onStop={() => {}} />)
      await userEvent.type(box(), 'next')
      expect(box()).toHaveValue('next')
    })
  })

  describe('the send error', () => {
    it('shows the caller text under the box, as an alert with an icon', () => {
      render(<Harness sendError="I'm still answering your last question." />)
      const alert = screen.getByRole('alert')
      expect(alert).toHaveTextContent("I'm still answering your last question.")
      expect(alert.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
      expect(box().compareDocumentPosition(alert) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    })

    it('shows nothing of its own when there is no send error', () => {
      render(<Harness />)
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    })
  })

  describe('a budget stop', () => {
    function renderDisabled(reason: 'sandbox' | 'daily') {
      return render(
        <MemoryRouter>
          <Harness initial="held" disabledReason={reason} />
        </MemoryRouter>,
      )
    }

    it.each([
      ['sandbox', "The assistant isn't available in this sandbox."],
      ['daily', "The assistant isn't available until tomorrow."],
    ] as const)(
      'disables the box and Ask, and says why in the placeholder (%s)',
      (reason, text) => {
        renderDisabled(reason)
        expect(box()).toBeDisabled()
        expect(box()).toHaveAttribute('placeholder', text)
        expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled()
      },
    )

    it('says the Handbook and the Directory still work, with both as links', () => {
      renderDisabled('sandbox')
      expect(screen.getByText(/You can still use the/)).toHaveTextContent(
        'You can still use the Handbook and the Directory.',
      )
      expect(screen.getByRole('link', { name: 'Handbook' })).toHaveAttribute('href', '/handbook')
      expect(screen.getByRole('link', { name: 'Directory' })).toHaveAttribute('href', '/directory')
    })

    it('skips the box and Ask in Tab order, and keeps the two links', async () => {
      renderDisabled('daily')
      await userEvent.tab()
      expect(screen.getByRole('link', { name: 'Handbook' })).toHaveFocus()
      await userEvent.tab()
      expect(screen.getByRole('link', { name: 'Directory' })).toHaveFocus()
    })

    it('still shows the AI disclosure', () => {
      renderDisabled('sandbox')
      expect(screen.getByText(AI_DISCLOSURE)).toBeInTheDocument()
    })

    it('sends nothing on Enter', () => {
      const onSubmit = vi.fn<(value: string) => void>()
      render(
        <MemoryRouter>
          <Harness initial="held" disabledReason="sandbox" onSubmit={onSubmit} />
        </MemoryRouter>,
      )
      fireEvent.keyDown(box(), { key: 'Enter' })
      expect(onSubmit).not.toHaveBeenCalled()
    })
  })

  describe('the length', () => {
    const hint = (count: number) => `${count.toLocaleString('en-US')} of 2,000 characters`

    it('says nothing below 1,800 characters', () => {
      render(<Harness initial={'a'.repeat(1799)} />)
      expect(screen.queryByText(/of 2,000 characters/)).not.toBeInTheDocument()
    })

    it('shows the count from 1,800, as plain text that is not read out on every key', () => {
      render(<Harness initial={'a'.repeat(1962)} />)
      const count = screen.getByText('1,962 of 2,000 characters')
      expect(count.tagName).toBe('P')
      expect(count.closest('[role="status"], output')).toBeNull()
      expect(box()).toHaveAccessibleDescription(`${AI_DISCLOSURE} 1,962 of 2,000 characters`)
    })

    it('shows the count at exactly 1,800 and at exactly 2,000, and still sends at 2,000', async () => {
      const onSubmit = vi.fn<(value: string) => void>()
      const first = render(<Harness initial={'a'.repeat(1800)} />)
      expect(screen.getByText(hint(1800))).toBeInTheDocument()
      first.unmount()
      render(<Harness initial={'a'.repeat(2000)} onSubmit={onSubmit} />)
      expect(screen.getByText(hint(2000))).toBeInTheDocument()
      expect(screen.queryByText(/Shorten your question/)).not.toBeInTheDocument()
      await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
      expect(onSubmit).toHaveBeenCalledTimes(1)
    })

    it('shows no hint for a draft whose real count is under 1,800, however many units it has', () => {
      // 1,000 emoji are 2,000 UTF-16 units and 1,000 characters.
      const first = render(<Harness initial={'👍'.repeat(1000)} />)
      expect(screen.queryByText(/of 2,000 characters/)).not.toBeInTheDocument()
      first.unmount()
      // 1,800 spaces trim to nothing.
      render(<Harness initial={' '.repeat(1800)} />)
      expect(screen.queryByText(/of 2,000 characters/)).not.toBeInTheDocument()
    })

    it('trims the way Python does: a leading U+FEFF counts, and a leading U+001F does not', async () => {
      const onSubmit = vi.fn<(value: string) => void>()
      const blocked = render(<Harness initial={`\uFEFF${'a'.repeat(2000)}`} onSubmit={onSubmit} />)
      expect(screen.getByText(/^2,001 of 2,000 characters\. Shorten/)).toBeInTheDocument()
      await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
      expect(onSubmit).not.toHaveBeenCalled()
      blocked.unmount()
      render(<Harness initial={`\u001f${'a'.repeat(2000)}`} onSubmit={onSubmit} />)
      expect(screen.getByText(hint(2000))).toBeInTheDocument()
      expect(screen.queryByText(/Shorten/)).not.toBeInTheDocument()
      await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
      expect(onSubmit).toHaveBeenCalledTimes(1)
    })

    it('treats a box of only U+001F as empty, as the API does', async () => {
      const onSubmit = vi.fn<(value: string) => void>()
      render(<Harness initial={'\u001f\u001f'} onSubmit={onSubmit} />)
      await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
      expect(onSubmit).not.toHaveBeenCalled()
      expect(box()).toHaveFocus()
    })

    it('counts the trimmed text, as the API does', () => {
      render(<Harness initial={`   ${'a'.repeat(1800)}   `} />)
      expect(screen.getByText(hint(1800))).toBeInTheDocument()
    })

    it('counts an emoji as one character, as Python does', () => {
      render(<Harness initial={'👍'.repeat(1800)} />)
      expect(screen.getByText(hint(1800))).toBeInTheDocument()
    })

    it('blocks sending from 2,001, saying how far over it is', async () => {
      const onSubmit = vi.fn<(value: string) => void>()
      render(<Harness initial={'a'.repeat(2001)} onSubmit={onSubmit} />)
      expect(
        screen.getByText('2,001 of 2,000 characters. Shorten your question to send it.'),
      ).toBeInTheDocument()
      await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
      await userEvent.type(box(), '{Enter}')
      expect(onSubmit).not.toHaveBeenCalled()
      expect(box()).toHaveAttribute('aria-invalid', 'true')
    })

    it('sends again once the question is shortened', async () => {
      const onSubmit = vi.fn<(value: string) => void>()
      render(<Harness initial={'a'.repeat(2001)} onSubmit={onSubmit} />)
      await userEvent.type(box(), '{Backspace}')
      await userEvent.type(box(), '{Enter}')
      expect(onSubmit).toHaveBeenCalledTimes(1)
    })

    it('does not set maxLength, which would cut a paste without saying so', () => {
      render(<Harness />)
      expect(box()).not.toHaveAttribute('maxlength')
    })
  })

  describe('the personal-data warning', () => {
    const WARNING =
      "That looks like a Social Security or card number. Please take it out; I can't take those."

    it('shows the caller text as an alert with the warning icon', () => {
      render(<Harness initial="my number is 123-45-6789" warning={WARNING} />)
      const alert = screen.getByRole('alert')
      expect(alert).toHaveTextContent(WARNING)
      expect(alert.querySelector('svg')).toHaveClass('text-warning')
    })

    it('blocks Ask and Enter while it is set', async () => {
      const onSubmit = vi.fn<(value: string) => void>()
      const blocked = render(
        <Harness initial="my number is 123-45-6789" warning={WARNING} onSubmit={onSubmit} />,
      )
      await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
      await userEvent.type(box(), '{Enter}')
      expect(onSubmit).not.toHaveBeenCalled()
      // The warning is about what the text holds, not a field that is wrong: no aria-invalid.
      expect(box()).not.toHaveAttribute('aria-invalid')
      blocked.unmount()
      render(<Harness initial="my number is 123-45-6789" onSubmit={onSubmit} />)
      await userEvent.type(box(), '{Enter}')
      expect(onSubmit).toHaveBeenCalledTimes(1)
    })
  })

  describe('aria-invalid', () => {
    it('is set for a question over the limit, and not otherwise', () => {
      const over = render(<Harness initial={'a'.repeat(2001)} />)
      expect(box()).toHaveAttribute('aria-invalid', 'true')
      over.unmount()
      render(<Harness initial={'a'.repeat(2000)} />)
      expect(box()).not.toHaveAttribute('aria-invalid')
    })

    it('is not set for the personal-data warning alone', () => {
      render(<Harness initial="my number is 123-45-6789" warning="Take it out." />)
      expect(box()).not.toHaveAttribute('aria-invalid')
    })
  })

  describe('the long-conversation notice', () => {
    it('shows nothing by default', () => {
      render(<Harness />)
      expect(screen.queryByText(/getting long/)).not.toBeInTheDocument()
    })

    it('shows the notice above the box, with a button that starts a new conversation', async () => {
      const onNewConversation = vi.fn<() => void>()
      render(<Harness longConversation onNewConversation={onNewConversation} />)
      const notice = screen.getByText(
        'This conversation is getting long, so answers may miss details from earlier messages. A new conversation starts clean.',
      )
      expect(notice.compareDocumentPosition(box()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
      await userEvent.click(screen.getByRole('button', { name: 'Start a new conversation' }))
      expect(onNewConversation).toHaveBeenCalledTimes(1)
    })

    it('has no button without a handler', () => {
      render(<Harness longConversation />)
      expect(
        screen.queryByRole('button', { name: 'Start a new conversation' }),
      ).not.toBeInTheDocument()
    })

    it('does not stop a question from sending', async () => {
      const onSubmit = vi.fn<(value: string) => void>()
      render(<Harness longConversation initial="One more" onSubmit={onSubmit} />)
      await userEvent.type(box(), '{Enter}')
      expect(onSubmit).toHaveBeenCalledTimes(1)
    })
  })

  describe('one line under the box at a time', () => {
    const lines = () => document.querySelectorAll('[data-slot="composer-line"]')

    // The value is a prop here, so a rerender can change it.
    function composer(props: Partial<React.ComponentProps<typeof Composer>>) {
      return (
        <MemoryRouter>
          <Composer value="" onChange={() => {}} onSubmit={() => {}} {...props} />
        </MemoryRouter>
      )
    }

    it('shows the budget stop line, then the length block, the warning, the send error, and the hint', () => {
      const all = {
        value: 'a'.repeat(2001),
        sendError: 'Still answering.',
        warning: 'Take the number out.',
        disabledReason: 'sandbox' as const,
      }
      const { rerender } = render(composer(all))
      expect(lines()).toHaveLength(1)
      expect(lines()[0]).toHaveTextContent('You can still use the Handbook and the Directory.')

      rerender(composer({ ...all, disabledReason: undefined }))
      expect(lines()).toHaveLength(1)
      expect(lines()[0]).toHaveTextContent('Shorten your question to send it.')

      rerender(composer({ ...all, disabledReason: undefined, value: 'a'.repeat(1900) }))
      expect(lines()).toHaveLength(1)
      expect(lines()[0]).toHaveTextContent('Take the number out.')

      rerender(
        composer({
          ...all,
          disabledReason: undefined,
          value: 'a'.repeat(1900),
          warning: undefined,
        }),
      )
      expect(lines()).toHaveLength(1)
      expect(lines()[0]).toHaveTextContent('Still answering.')

      rerender(
        composer({
          ...all,
          disabledReason: undefined,
          value: 'a'.repeat(1900),
          warning: undefined,
          sendError: undefined,
        }),
      )
      expect(lines()).toHaveLength(1)
      expect(lines()[0]).toHaveTextContent('1,900 of 2,000 characters')
    })

    it('shows the budget stop links even with a send error or a warning set', () => {
      render(
        composer({
          value: 'short',
          sendError: 'Still answering.',
          warning: 'No.',
          disabledReason: 'daily',
        }),
      )
      expect(lines()).toHaveLength(1)
      expect(screen.getByRole('link', { name: 'Handbook' })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'Directory' })).toBeInTheDocument()
      expect(screen.queryByText('Still answering.')).not.toBeInTheDocument()
    })

    it('shows the over-limit block, not a send error left over from before', () => {
      render(
        composer({ value: 'a'.repeat(2100), sendError: "I'm still answering your last question." }),
      )
      expect(lines()).toHaveLength(1)
      expect(lines()[0]).toHaveTextContent(
        '2,100 of 2,000 characters. Shorten your question to send it.',
      )
      expect(screen.queryByText(/still answering/)).not.toBeInTheDocument()
    })

    it('hands focus to the Handbook link when a budget stop arrives with a send error showing', () => {
      const { rerender } = render(composer({ sendError: 'Still answering.' }))
      box().focus()
      rerender(composer({ sendError: 'Still answering.', disabledReason: 'daily' }))
      expect(screen.getByRole('link', { name: 'Handbook' })).toHaveFocus()
    })

    it('has no line at all when nothing applies', () => {
      render(composer({ value: 'a question' }))
      expect(lines()).toHaveLength(0)
    })

    it('shows the hint at exactly 2,000 and the block from 2,001, never both', () => {
      const { rerender } = render(composer({ value: 'a'.repeat(2000) }))
      expect(lines()[0]).toHaveTextContent('2,000 of 2,000 characters')
      expect(lines()[0]).not.toHaveTextContent('Shorten')
      rerender(composer({ value: 'a'.repeat(2001) }))
      expect(lines()).toHaveLength(1)
      expect(lines()[0]).toHaveTextContent('Shorten your question to send it.')
    })
  })

  it('describes the box with the line under it, as well as the disclosure', () => {
    render(<Composer value={'a'.repeat(1900)} onChange={() => {}} onSubmit={() => {}} />)
    expect(box()).toHaveAccessibleDescription(`${AI_DISCLOSURE} 1,900 of 2,000 characters`)
  })

  describe('what a screen reader is told about the length', () => {
    // The hidden status is always in the page, so it is already watched when its text changes.
    const spoken = () => screen.getByRole('status', { name: '' })
    function Typing({ start }: { start: string }) {
      const [value, setValue] = useState(start)
      return (
        <>
          <Composer value={value} onChange={setValue} onSubmit={() => {}} />
          <button type="button" onClick={() => setValue((v) => v + 'a')}>
            more
          </button>
          <button type="button" onClick={() => setValue((v) => v.slice(0, -1))}>
            fewer
          </button>
        </>
      )
    }

    it('is in the page, empty, and hidden from sight', () => {
      render(<Typing start="hello" />)
      expect(spoken()).toHaveTextContent('')
      expect(spoken()).toHaveClass('sr-only')
    })

    it('says nothing for a draft that was already long when the page loaded', () => {
      render(<Typing start={'a'.repeat(1900)} />)
      expect(spoken()).toHaveTextContent('')
    })

    it('says the count once, on first reaching 1,800, and not on each key after', async () => {
      render(<Typing start={'a'.repeat(1799)} />)
      await userEvent.click(screen.getByRole('button', { name: 'more' }))
      expect(spoken()).toHaveTextContent('1,800 of 2,000 characters')
      await userEvent.click(screen.getByRole('button', { name: 'more' }))
      expect(spoken()).toHaveTextContent(/^1,800 of 2,000 characters$/)
    })

    it('says so on going over 2,000, and when it is back under', async () => {
      render(<Typing start={'a'.repeat(2000)} />)
      await userEvent.click(screen.getByRole('button', { name: 'more' }))
      expect(spoken()).toHaveTextContent(
        '2,001 of 2,000 characters. Shorten your question to send it.',
      )
      await userEvent.click(screen.getByRole('button', { name: 'fewer' }))
      expect(spoken()).toHaveTextContent('Back under the limit.')
    })

    it('says nothing for emoji that are many units and few characters', async () => {
      // 1,799 units, then 1,800: still only 900 characters.
      render(<Typing start={`${'👍'.repeat(899)}a`} />)
      await userEvent.click(screen.getByRole('button', { name: 'more' }))
      expect(spoken()).toHaveTextContent('')
    })

    it('clears what it said when the draft drops below 1,800 again', async () => {
      render(<Typing start={'a'.repeat(1799)} />)
      await userEvent.click(screen.getByRole('button', { name: 'more' }))
      expect(spoken()).toHaveTextContent('1,800 of 2,000 characters')
      await userEvent.click(screen.getByRole('button', { name: 'fewer' }))
      expect(spoken()).toHaveTextContent('')
    })
  })

  describe('Ask while sending is blocked', () => {
    it('is aria-disabled over the limit, stays focusable, and pressing it focuses the box', async () => {
      const onSubmit = vi.fn<(value: string) => void>()
      render(<Harness initial={'a'.repeat(2001)} onSubmit={onSubmit} />)
      const ask = screen.getByRole('button', { name: 'Ask' })
      expect(ask).toHaveAttribute('aria-disabled', 'true')
      expect(ask).toBeEnabled()
      await userEvent.click(ask)
      expect(onSubmit).not.toHaveBeenCalled()
      expect(box()).toHaveFocus()
    })

    it('is aria-disabled while the personal-data warning is set', async () => {
      render(<Harness initial="my number is 123-45-6789" warning="Take it out." />)
      expect(screen.getByRole('button', { name: 'Ask' })).toHaveAttribute('aria-disabled', 'true')
    })

    it('is not aria-disabled otherwise', () => {
      render(<Harness initial="a question" />)
      expect(screen.getByRole('button', { name: 'Ask' })).not.toHaveAttribute('aria-disabled')
    })
  })

  describe('a budget stop keeps its links', () => {
    it('shows the Handbook and Directory line even with a long draft', () => {
      render(
        <MemoryRouter>
          <Composer
            value={'a'.repeat(2100)}
            onChange={() => {}}
            onSubmit={() => {}}
            disabledReason="sandbox"
          />
        </MemoryRouter>,
      )
      expect(screen.getByRole('link', { name: 'Handbook' })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'Directory' })).toBeInTheDocument()
      expect(screen.queryByText(/of 2,000 characters/)).not.toBeInTheDocument()
    })
  })

  describe('the docked variant, for the conversation', () => {
    it('starts at one row, and the home composer keeps its three', () => {
      const { rerender } = render(<Harness variant="docked" />)
      expect(box()).toHaveAttribute('rows', '1')
      rerender(<Harness />)
      expect(box()).toHaveAttribute('rows', '3')
      rerender(<Harness variant="default" />)
      expect(box()).toHaveAttribute('rows', '3')
    })

    it('grows with its text up to about four lines, then scrolls', () => {
      render(<Harness variant="docked" />)
      expect(box()).toHaveClass('field-sizing-content', 'max-h-35', 'overflow-y-auto')
    })

    it('has no growth classes on the home composer', () => {
      render(<Harness />)
      expect(box()).not.toHaveClass('field-sizing-content')
    })

    it('resizes itself to its text where the browser has no field-sizing', async () => {
      vi.stubGlobal('CSS', { supports: () => false }) // Firefox and Safari
      const scrollHeight = vi
        .spyOn(HTMLTextAreaElement.prototype, 'scrollHeight', 'get')
        .mockReturnValue(96)
      try {
        render(<Harness variant="docked" />)
        await userEvent.type(box(), 'a')
        expect(box().style.height).toBe('96px')
      } finally {
        scrollHeight.mockRestore()
        vi.unstubAllGlobals()
      }
    })

    it('does not resize it by hand where the browser sizes it', async () => {
      vi.stubGlobal('CSS', { supports: () => true })
      const scrollHeight = vi
        .spyOn(HTMLTextAreaElement.prototype, 'scrollHeight', 'get')
        .mockReturnValue(96)
      try {
        render(<Harness variant="docked" />)
        await userEvent.type(box(), 'a')
        expect(box().style.height).toBe('')
      } finally {
        scrollHeight.mockRestore()
        vi.unstubAllGlobals()
      }
    })

    it('clears the height it set when the box stops being docked', async () => {
      vi.stubGlobal('CSS', { supports: () => false })
      const scrollHeight = vi
        .spyOn(HTMLTextAreaElement.prototype, 'scrollHeight', 'get')
        .mockReturnValue(96)
      try {
        const { rerender } = render(<Harness variant="docked" />)
        await userEvent.type(box(), 'a')
        expect(box().style.height).toBe('96px')
        rerender(<Harness variant="default" />)
        expect(box().style.height).toBe('')
      } finally {
        scrollHeight.mockRestore()
        vi.unstubAllGlobals()
      }
    })

    it('leaves the height alone on the home composer', async () => {
      const scrollHeight = vi
        .spyOn(HTMLTextAreaElement.prototype, 'scrollHeight', 'get')
        .mockReturnValue(96)
      try {
        render(<Harness />)
        await userEvent.type(box(), 'a')
        expect(box().style.height).toBe('')
      } finally {
        scrollHeight.mockRestore()
      }
    })
  })

  describe('the footer below sm', () => {
    it('puts the docked disclosure on its own row above the button, with the button at the end', () => {
      render(<Harness variant="docked" />)
      const disclosure = screen.getByText(AI_DISCLOSURE).closest('p')!
      expect(disclosure).toHaveClass('max-sm:basis-full')
      expect(screen.getByRole('button', { name: 'Ask' })).toHaveClass('max-sm:ml-auto')
    })

    it('does the same for the docked Stop', () => {
      render(<Harness variant="docked" streaming />)
      expect(screen.getByRole('button', { name: 'Stop' })).toHaveClass('max-sm:ml-auto')
    })

    it('leaves the home composer beside its button, as the home design draws it', () => {
      render(<Harness />)
      const disclosure = screen.getByText(AI_DISCLOSURE).closest('p')!
      expect(disclosure).not.toHaveClass('max-sm:basis-full')
      expect(disclosure).toHaveClass('flex-1')
      expect(screen.getByRole('button', { name: 'Ask' })).not.toHaveClass('max-sm:ml-auto')
    })

    it("leaves the home composer's Stop beside the disclosure too", () => {
      render(<Harness streaming />)
      expect(screen.getByRole('button', { name: 'Stop' })).not.toHaveClass('max-sm:ml-auto')
    })
  })

  describe('focus when the composer changes under it', () => {
    const composer = (props: Partial<React.ComponentProps<typeof Composer>>) => (
      <MemoryRouter>
        <Composer value="a draft" onChange={() => {}} onSubmit={() => {}} {...props} />
        <button type="button">elsewhere</button>
      </MemoryRouter>
    )

    it('moves focus to the box when the answer finishes while Stop has focus', () => {
      const { rerender } = render(composer({ streaming: true, onStop: () => {} }))
      screen.getByRole('button', { name: 'Stop' }).focus()
      expect(screen.getByRole('button', { name: 'Stop' })).toHaveFocus()
      rerender(composer({ streaming: false }))
      expect(box()).toHaveFocus()
    })

    it('leaves focus alone when the answer finishes and Stop did not have it', () => {
      const { rerender } = render(composer({ streaming: true, onStop: () => {} }))
      box().focus()
      rerender(composer({ streaming: false }))
      expect(box()).toHaveFocus()
      rerender(composer({ streaming: true, onStop: () => {} }))
      screen.getByRole('button', { name: 'elsewhere' }).focus()
      rerender(composer({ streaming: false }))
      expect(screen.getByRole('button', { name: 'elsewhere' })).toHaveFocus()
    })

    it('does not take focus when Stop had it earlier and the person has since moved on', () => {
      const { rerender } = render(composer({ streaming: true, onStop: () => {} }))
      screen.getByRole('button', { name: 'Stop' }).focus()
      screen.getByRole('button', { name: 'elsewhere' }).focus()
      rerender(composer({ streaming: false }))
      expect(screen.getByRole('button', { name: 'elsewhere' })).toHaveFocus()
    })

    it('does not take focus when the answer finishes and focus was in the box, then went nowhere', () => {
      const { rerender } = render(composer({ streaming: true, onStop: () => {} }))
      box().focus()
      box().blur()
      expect(document.body).toHaveFocus()
      rerender(composer({ streaming: false }))
      expect(document.body).toHaveFocus()
    })

    it('does not take focus at the end of an answer when the person clicked away from Stop to plain text', async () => {
      const { rerender } = render(composer({ streaming: true, onStop: () => {} }))
      const stop = screen.getByRole('button', { name: 'Stop' })
      stop.focus()
      stop.blur() // focus goes nowhere: the focusout has no relatedTarget
      await Promise.resolve()
      rerender(composer({ streaming: false }))
      expect(document.body).toHaveFocus()
    })

    it('does not take focus for a budget stop when the person clicked away from the box to plain text', async () => {
      const { rerender } = render(composer({}))
      box().focus()
      box().blur()
      await Promise.resolve()
      rerender(composer({ disabledReason: 'daily' }))
      expect(document.body).toHaveFocus()
    })

    it('still hands focus on when Stop is removed and the browser reports a focusout for it', async () => {
      const { rerender } = render(composer({ streaming: true, onStop: () => {} }))
      const stop = screen.getByRole('button', { name: 'Stop' })
      stop.focus()
      // Some browsers report a focusout, with nothing to move to, as the focused node is removed.
      stop.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: null }))
      rerender(composer({ streaming: false }))
      await Promise.resolve()
      expect(box()).toHaveFocus()
      // The removed Stop's focusout must not have cleared where focus is now: the box. So a budget
      // stop that disables the box still finds focus to hand on.
      rerender(composer({ disabledReason: 'daily' }))
      expect(screen.getByRole('link', { name: 'Handbook' })).toHaveFocus()
    })

    it('moves focus to Stop when the answer starts while Ask has focus', () => {
      const { rerender } = render(composer({}))
      screen.getByRole('button', { name: 'Ask' }).focus()
      rerender(composer({ streaming: true, onStop: () => {} }))
      expect(screen.getByRole('button', { name: 'Stop' })).toHaveFocus()
    })

    it('leaves focus alone when the answer starts and it was in the box', () => {
      const { rerender } = render(composer({}))
      box().focus()
      rerender(composer({ streaming: true, onStop: () => {} }))
      expect(box()).toHaveFocus()
    })

    it('leaves focus alone when the answer starts and it was elsewhere', () => {
      const { rerender } = render(composer({}))
      screen.getByRole('button', { name: 'elsewhere' }).focus()
      rerender(composer({ streaming: true, onStop: () => {} }))
      expect(screen.getByRole('button', { name: 'elsewhere' })).toHaveFocus()
    })

    it('does not take focus for Stop when Ask had it and the person has since clicked away', async () => {
      const { rerender } = render(composer({}))
      const ask = screen.getByRole('button', { name: 'Ask' })
      ask.focus()
      ask.blur()
      await Promise.resolve()
      rerender(composer({ streaming: true, onStop: () => {} }))
      expect(document.body).toHaveFocus()
    })

    it('moves focus to the Handbook link when a budget stop disables the box under focus', () => {
      const { rerender } = render(composer({}))
      box().focus()
      rerender(composer({ disabledReason: 'daily' }))
      expect(screen.getByRole('link', { name: 'Handbook' })).toHaveFocus()
    })

    it('does the same when Ask has focus', () => {
      const { rerender } = render(composer({}))
      screen.getByRole('button', { name: 'Ask' }).focus()
      rerender(composer({ disabledReason: 'sandbox' }))
      expect(screen.getByRole('link', { name: 'Handbook' })).toHaveFocus()
    })

    it('leaves focus alone when a budget stop arrives and focus was elsewhere', () => {
      const { rerender } = render(composer({}))
      screen.getByRole('button', { name: 'elsewhere' }).focus()
      rerender(composer({ disabledReason: 'daily' }))
      expect(screen.getByRole('button', { name: 'elsewhere' })).toHaveFocus()
    })

    it('does not move focus when it was never in the composer', () => {
      const { rerender } = render(composer({}))
      rerender(composer({ disabledReason: 'daily' }))
      expect(document.body).toHaveFocus()
    })
  })
})
