import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SandboxIndicator } from '@/components/status/sandbox-indicator'
import { ConversationHeader, RetentionLine } from './conversation-header'

const RETENTION = 'Conversations are deleted with your sandbox after 24 hours.'

describe('RetentionLine', () => {
  it('says conversations are deleted with the sandbox after 24 hours', () => {
    render(<RetentionLine />)
    expect(screen.getByText(RETENTION)).toBeInTheDocument()
  })
})

describe('ConversationHeader', () => {
  it('has the retention line, the new-conversation button, and the sandbox pill', () => {
    render(
      <ConversationHeader onNewConversation={() => {}}>
        <SandboxIndicator>Sandbox resets in 21 h</SandboxIndicator>
      </ConversationHeader>,
    )
    expect(screen.getByText(RETENTION)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start a new conversation' })).toBeInTheDocument()
    expect(screen.getByText('Sandbox resets in 21 h')).toBeInTheDocument()
  })

  it('calls the handler when the button is pressed', async () => {
    const onNewConversation = vi.fn<() => void>()
    render(<ConversationHeader onNewConversation={onNewConversation} />)
    await userEvent.click(screen.getByRole('button', { name: 'Start a new conversation' }))
    expect(onNewConversation).toHaveBeenCalledTimes(1)
  })

  it('draws the button with an icon, and names it by its label at every width', () => {
    render(<ConversationHeader onNewConversation={() => {}} />)
    const button = screen.getByRole('button', { name: 'Start a new conversation' })
    expect(button.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
    // Below 640 px the words go from sight but stay in the name, and the button is square.
    expect(screen.getAllByText('Start a new conversation')[0]).toHaveClass('max-sm:sr-only')
    expect(button).toHaveClass('max-sm:size-8')
  })

  it('hides the retention line at narrow widths, for the page to show under the composer', () => {
    render(<ConversationHeader onNewConversation={() => {}} />)
    expect(screen.getByText(RETENTION)).toHaveClass('max-sm:hidden')
  })

  it('works with no sandbox pill', () => {
    render(<ConversationHeader onNewConversation={() => {}} />)
    expect(screen.queryByText(/Sandbox resets/)).not.toBeInTheDocument()
  })
})
