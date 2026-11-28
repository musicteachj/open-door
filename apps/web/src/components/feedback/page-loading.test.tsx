import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PAGE_LOADING_DELAY_MS, PageLoading } from './page-loading'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('PageLoading', () => {
  it('tells a screen reader at once, and shows nothing for a fast load', () => {
    const { container } = render(<PageLoading />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading…')
    act(() => vi.advanceTimersByTime(PAGE_LOADING_DELAY_MS - 1))
    expect(container.querySelector('[aria-hidden="true"]')).toBeNull()
  })

  it('fades in a spinner and the words after the delay, hidden from assistive technology', () => {
    const { container } = render(<PageLoading text="Loading the page…" />)
    act(() => vi.advanceTimersByTime(PAGE_LOADING_DELAY_MS))
    const shown = container.querySelector<HTMLElement>('[aria-hidden="true"]')!
    expect(shown).toHaveClass('motion-safe:animate-fade-in')
    expect(shown).toHaveTextContent('Loading the page…')
    expect(shown.querySelector('.animate-spin')).not.toBeNull()
    // One status, so the words are heard once.
    expect(screen.getAllByRole('status')).toHaveLength(1)
  })

  it('shows what the page gives it in place of the spinner line', () => {
    render(<PageLoading>{<p>a skeleton</p>}</PageLoading>)
    act(() => vi.advanceTimersByTime(PAGE_LOADING_DELAY_MS))
    expect(screen.getByText('a skeleton')).toBeInTheDocument()
  })
})
