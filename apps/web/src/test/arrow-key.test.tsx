import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRef } from 'react'
import { describe, expect, it } from 'vitest'
import { arrow } from './arrow-key'

// A list that moves focus to the second button a while after the key goes down, like a queue that
// reloads after a filter change before its rows can take focus again.
function SlowList({ delayMs }: { delayMs: number }) {
  const second = useRef<HTMLButtonElement>(null)
  return (
    <>
      <button
        type="button"
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown') setTimeout(() => second.current?.focus(), delayMs)
        }}
      >
        First
      </button>
      <button type="button" ref={second}>
        Second
      </button>
    </>
  )
}

describe('arrow', () => {
  it('waits for focus that moves after 800 ms, which a loaded runner can take', async () => {
    const user = userEvent.setup()
    render(<SlowList delayMs={800} />)
    screen.getByRole('button', { name: 'First' }).focus()
    await arrow(user, 'ArrowDown')
    expect(screen.getByRole('button', { name: 'Second' })).toHaveFocus()
  })

  it('still returns for a key that moves nothing', async () => {
    const user = userEvent.setup()
    render(<SlowList delayMs={60_000} />)
    screen.getByRole('button', { name: 'First' }).focus()
    const started = Date.now()
    await arrow(user, 'ArrowDown')
    expect(Date.now() - started).toBeLessThan(3000)
  })
})
