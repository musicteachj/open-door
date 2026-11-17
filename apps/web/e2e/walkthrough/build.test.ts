import { describe, expect, it } from 'vitest'
import {
  exchangesOf,
  holdMs,
  localIsoDate,
  NOTES,
  summaryNote,
  withoutLinks,
  type RecordedTurn,
} from './build'

const turn = (overrides: Partial<RecordedTurn>): RecordedTurn => ({
  question: 'How many sick days do I get?',
  status: 'completed',
  answerText: 'You get 40 hours.',
  citations: [],
  escalation: null,
  ...overrides,
})

const citation = (sectionId: string, title: string, groupName = 'Time off') => ({
  sectionId,
  title,
  groupName,
})

describe('holdMs: long enough to read', () => {
  it('is about 4 s plus 1 s for every 15 words', () => {
    expect(holdMs('')).toBe(4000)
    expect(holdMs(Array(15).fill('word').join(' '))).toBe(5000)
    expect(holdMs(Array(30).fill('word').join(' '))).toBe(6000)
    expect(holdMs(Array(22).fill('word').join(' '))).toBe(5467)
  })
})

describe('exchangesOf: the transcript of a step’s turns', () => {
  it('pairs each question with its answer, as stored', () => {
    expect(exchangesOf([turn({})])).toEqual([
      { speaker: 'person', text: 'How many sick days do I get?' },
      { speaker: 'ai', text: 'You get 40 hours.' },
    ])
  })

  it('lists each cited section once, in order, as its number and title', () => {
    const answer = exchangesOf([
      turn({
        citations: [
          citation('CA-4.3', 'Sick leave', 'California addendum'),
          citation('4.1', 'Paid time off'),
          citation('CA-4.3', 'Sick leave', 'California addendum'),
        ],
      }),
    ])[1]
    expect(answer).toEqual({
      speaker: 'ai',
      text: 'You get 40 hours.',
      sources: [
        { id: 'CA-4.3', title: 'Sick leave' },
        { id: '4.1', title: 'Paid time off' },
      ],
    })
  })

  it('records the HR panel’s fixed text as the panel’s, never as an answer', () => {
    const exchanges = exchangesOf([
      turn({
        question: 'My manager keeps making comments about my age.',
        answerText: '',
        escalation: { kind: 'sensitive', message: 'This sounds like something a person…' },
      }),
    ])
    expect(exchanges[1]).toEqual({
      speaker: 'hr-panel',
      text: 'This sounds like something a person…',
    })
  })

  it('refuses a turn with no answer and no panel: the take is not usable', () => {
    expect(() => exchangesOf([turn({ answerText: '  ' })])).toThrow(/no answer/)
  })

  it('drops links from an answer: the public page can’t open them', () => {
    expect(
      exchangesOf([
        turn({ answerText: 'See [sick leave](/handbook/4.3) and [Leo](/directory/x).' }),
      ])[1],
    ).toMatchObject({ text: 'See sick leave and Leo.' })
  })
})

describe('withoutLinks', () => {
  it.each([
    ['[a](/b)', 'a'],
    ['**[bold link](/x)** text', '**bold link** text'],
    ['no links here', 'no links here'],
    ['[a](/b) and [c](https://d.example)', 'a and c'],
    ['a [bracket] alone', 'a [bracket] alone'],
  ])('%s becomes %s', (input, output) => {
    expect(withoutLinks(input)).toBe(output)
  })
})

describe('the notes (approved 2026-11-15)', () => {
  it('say what the person did, in the approved words', () => {
    expect(NOTES).toEqual({
      'book-day-off': 'Priya confirmed the card. The request went to Marcus Bell.',
      'decide-as-manager': 'Marcus confirmed. Priya’s request is approved.',
      sensitive: 'Priya sent a confidential case to HR in her own words.',
    })
  })

  it('quote the case summary the AI wrote on step 8', () => {
    expect(summaryNote('  The employee reports a concern.\n')).toBe(
      'Dana opened Priya’s case. The AI’s summary: “The employee reports a concern.” Priya’s own words stayed hidden.',
    )
  })
})

describe('localIsoDate', () => {
  it('is the local calendar day, with two-digit month and day', () => {
    expect(localIsoDate(new Date(2026, 0, 5, 23, 30))).toBe('2026-01-05')
    expect(localIsoDate(new Date(2026, 10, 16, 0, 5))).toBe('2026-11-16')
  })
})
