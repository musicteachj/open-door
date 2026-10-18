import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ANNOUNCE_DELAY_MS, announce, installAnnouncer, resetAnnouncer } from './announce'

const regions = () => document.querySelectorAll('[data-slot="announcer"] [aria-live]')
const polite = () => document.querySelector('[data-slot="announcer"] [aria-live="polite"]')!
const assertive = () => document.querySelector('[data-slot="announcer"] [aria-live="assertive"]')!

describe('announce', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    resetAnnouncer()
    vi.useRealTimers()
  })

  it('puts nothing in the page until the first announcement', () => {
    expect(document.querySelector('[data-slot="announcer"]')).toBeNull()
  })

  it('creates one polite and one assertive region on the body, once, hidden from sight', () => {
    announce('One')
    announce('Two')
    announce('Three', 'assertive')
    expect(document.querySelectorAll('[data-slot="announcer"]')).toHaveLength(1)
    expect(document.querySelector('[data-slot="announcer"]')!.parentElement).toBe(document.body)
    expect(regions()).toHaveLength(2)
    expect(polite()).toBeInTheDocument()
    expect(assertive()).toBeInTheDocument()
    expect(document.querySelector('[data-slot="announcer"]')).toHaveClass('sr-only')
  })

  it('has regions that are in the page before any text is set', () => {
    announce('Hello')
    expect(polite()).toBeEmptyDOMElement()
    expect(assertive()).toBeEmptyDOMElement()
  })

  it('sets the text after a short delay, not in the same instant', () => {
    announce('Searching the handbook')
    expect(polite()).toHaveTextContent('')
    vi.advanceTimersByTime(ANNOUNCE_DELAY_MS - 1)
    expect(polite()).toHaveTextContent('')
    vi.advanceTimersByTime(1)
    expect(polite()).toHaveTextContent('Searching the handbook')
  })

  it('is polite by default, and sends an assertive message to the assertive region only', () => {
    announce('Quietly')
    announce('Right now', 'assertive')
    vi.advanceTimersByTime(ANNOUNCE_DELAY_MS)
    expect(polite()).toHaveTextContent('Quietly')
    expect(assertive()).toHaveTextContent('Right now')
    expect(polite()).not.toHaveTextContent('Right now')
    expect(assertive()).not.toHaveTextContent('Quietly')
  })

  it('clears the region before it repeats a message, so the same words are read again', () => {
    announce('Same words')
    vi.advanceTimersByTime(ANNOUNCE_DELAY_MS)
    expect(polite()).toHaveTextContent('Same words')
    announce('Same words')
    expect(polite()).toHaveTextContent('')
    vi.advanceTimersByTime(ANNOUNCE_DELAY_MS)
    expect(polite()).toHaveTextContent('Same words')
  })

  it('says only the latest of two announcements made in quick succession', () => {
    announce('First')
    vi.advanceTimersByTime(ANNOUNCE_DELAY_MS - 10)
    announce('Second')
    // When "First" would have been said, nothing is, and only "Second" ever is.
    vi.advanceTimersByTime(10)
    expect(polite()).toHaveTextContent('')
    vi.advanceTimersByTime(ANNOUNCE_DELAY_MS)
    expect(polite()).toHaveTextContent(/^Second$/)
  })

  it('does not let an earlier message empty the region under a later one', () => {
    announce('First')
    vi.advanceTimersByTime(ANNOUNCE_DELAY_MS)
    vi.advanceTimersByTime(6_900)
    announce('Second')
    vi.advanceTimersByTime(ANNOUNCE_DELAY_MS)
    // The first message's clearing time passes while the second is on show.
    vi.advanceTimersByTime(200)
    expect(polite()).toHaveTextContent(/^Second$/)
  })

  it('empties the region again after a while, so the words are not left for a reader to find', () => {
    announce('Said')
    vi.advanceTimersByTime(ANNOUNCE_DELAY_MS)
    vi.advanceTimersByTime(10_000)
    expect(polite()).toHaveTextContent('')
  })

  it('leaves nothing behind after a reset, and starts clean', () => {
    announce('One')
    resetAnnouncer()
    expect(document.querySelector('[data-slot="announcer"]')).toBeNull()
    vi.advanceTimersByTime(20_000)
    expect(document.querySelector('[data-slot="announcer"]')).toBeNull()
    announce('Two')
    expect(document.querySelectorAll('[data-slot="announcer"]')).toHaveLength(1)
  })

  describe('installAnnouncer', () => {
    it('puts both regions on the body, empty, before anything is announced', () => {
      installAnnouncer()
      expect(document.querySelectorAll('[data-slot="announcer"]')).toHaveLength(1)
      expect(regions()).toHaveLength(2)
      expect(polite()).toBeEmptyDOMElement()
      expect(assertive()).toBeEmptyDOMElement()
    })

    it('is safe to call twice, and announcing after it uses the same regions', () => {
      installAnnouncer()
      const root = document.querySelector('[data-slot="announcer"]')
      installAnnouncer()
      announce('Hello')
      vi.advanceTimersByTime(ANNOUNCE_DELAY_MS)
      expect(document.querySelectorAll('[data-slot="announcer"]')).toHaveLength(1)
      expect(document.querySelector('[data-slot="announcer"]')).toBe(root)
      expect(polite()).toHaveTextContent('Hello')
    })

    it('makes a new pair if the regions were taken out of the page', () => {
      installAnnouncer()
      document.querySelector('[data-slot="announcer"]')!.remove()
      installAnnouncer()
      expect(document.querySelectorAll('[data-slot="announcer"]')).toHaveLength(1)
    })
  })
})
