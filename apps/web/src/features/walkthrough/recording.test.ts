import { describe, expect, it } from 'vitest'
import { TOUR_END_SUMMARY } from '@/components/tour/end-card-copy'
import { PERSONAS } from '@/features/personas/personas'
import { TOUR } from '@/features/tour/script'
import { formatDuration, formatRecordedOn, metadataLine, WALKTHROUGH } from './recording'

// The transcript is the video's text alternative, so it must say what the video shows. The
// recording writes it from the tour's own script; if the tour's words change, this fails until the
// video is recorded again (CLAUDE.md: re-record when the tour changes visibly).

describe('walkthrough.json', () => {
  it('has one step per tour step, in the tour’s order', () => {
    expect(WALKTHROUGH.steps.map((step) => step.id)).toEqual(TOUR.map((step) => step.id))
  })

  it.each(TOUR.map((step, index) => [step.id, index] as const))(
    'step %s has the tour’s title, persona, and words',
    (_id, index) => {
      const tour = TOUR[index]
      const step = WALKTHROUGH.steps[index]
      expect(step.title).toBe(tour.title)
      const last = index === TOUR.length - 1
      expect(step.persona).toBe(last ? null : tour.persona)
      expect(step.words).toBe(last ? TOUR_END_SUMMARY : tour.body)
    },
  )

  it('names only the four personas', () => {
    const keys = new Set<string>(PERSONAS.map((persona) => persona.key))
    const named = WALKTHROUGH.steps.flatMap((step) => (step.persona ? [step.persona] : []))
    expect(named.filter((key) => !keys.has(key))).toEqual([])
  })

  it('asks each step’s questions as the tour’s chips, each followed by its reply', () => {
    const asked = WALKTHROUGH.steps.map((step) =>
      step.exchanges.filter((e) => e.speaker === 'person').map((e) => e.text),
    )
    expect(asked).toEqual(TOUR.map((tour) => [...(tour.chips ?? [])]))
    // Question, reply, question, reply: never two of one kind in a row, and never a reply first.
    const pattern = WALKTHROUGH.steps.map((step) =>
      step.exchanges.map((e) => (e.speaker === 'person' ? 'Q' : 'R')).join(''),
    )
    expect(pattern.filter((p) => !/^(QR)*$/.test(p))).toEqual([])
  })

  it('has words in every exchange, and sources only on the AI’s answers', () => {
    const exchanges = WALKTHROUGH.steps.flatMap((step) => step.exchanges)
    expect(exchanges.filter((e) => e.text.trim() === '')).toEqual([])
    expect(exchanges.filter((e) => e.speaker !== 'ai' && 'sources' in e)).toEqual([])
    // The page is public, so an answer keeps no link (the recording drops them).
    expect(exchanges.filter((e) => /\]\([^)]*\)/.test(e.text))).toEqual([])
    const sources = exchanges.flatMap((e) => (e.speaker === 'ai' ? (e.sources ?? []) : []))
    expect(sources.filter((x) => x.id.trim() === '' || x.title.trim() === '')).toEqual([])
  })

  it('has the date, the model, and a length', () => {
    expect(WALKTHROUGH.recordedOn).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(Number.isNaN(Date.parse(WALKTHROUGH.recordedOn))).toBe(false)
    expect(WALKTHROUGH.model).toMatch(/^Claude /)
    expect(WALKTHROUGH.durationSeconds).toBeGreaterThan(0)
  })
})

describe('the metadata line', () => {
  it.each([
    [150, '2 min 30 s'],
    [120, '2 min'],
    [45, '45 s'],
    [59.6, '1 min'],
    [0, '0 s'],
  ])('says %s seconds as "%s"', (seconds, said) => {
    expect(formatDuration(seconds)).toBe(said)
  })

  it('says the date the same way in every time zone', () => {
    expect(formatRecordedOn('2026-10-26')).toBe('October 26, 2026')
    expect(formatRecordedOn('2027-01-01')).toBe('January 1, 2027')
  })

  it('reads as screen 16 draws it', () => {
    expect(
      metadataLine({ recordedOn: '2026-10-26', model: 'Claude Opus 5.5', durationSeconds: 150 }),
    ).toBe('Recorded October 26, 2026 · Claude Opus 5.5 · 2 min 30 s · No sound')
  })
})
