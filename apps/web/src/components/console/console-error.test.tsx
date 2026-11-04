import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ConsoleError } from './console-error'

describe('ConsoleError', () => {
  it('says what failed, gives the reference, and offers Retry', async () => {
    const onRetry = vi.fn<() => void>()
    render(<ConsoleError reference="c41e8b07" onRetry={onRetry} />)
    expect(
      screen.getByRole('heading', { level: 3, name: 'Something went wrong on our side.' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        'The sandbox figures didn’t load. Try again in a moment. If it keeps happening, this reference helps us find it:',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('c41e8b07').tagName).toBe('CODE')
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('leaves out the reference line when there is none', () => {
    render(<ConsoleError onRetry={() => {}} />)
    expect(screen.queryByText(/Reference/)).toBeNull()
    expect(
      screen.getByText('The sandbox figures didn’t load. Try again in a moment.'),
    ).toBeInTheDocument()
  })

  it('does not take focus when it appears', () => {
    render(<ConsoleError reference="c41e8b07" onRetry={() => {}} />)
    expect(document.body).toHaveFocus()
  })
})
