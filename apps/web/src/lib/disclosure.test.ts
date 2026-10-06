import { describe, expect, it } from 'vitest'
import { AI_DISCLOSURE } from './disclosure'

describe('AI_DISCLOSURE', () => {
  it('says what the assistant is, in the design’s words', () => {
    expect(AI_DISCLOSURE).toBe(
      'Open Door is an AI assistant. It can make mistakes, and it always shows its sources.',
    )
  })
})
