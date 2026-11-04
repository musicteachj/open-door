import { describe, expect, it } from 'vitest'
import { modelDisplayName } from './models'

describe('models', () => {
  it('names a Claude model, and falls back to the raw id', () => {
    expect(modelDisplayName('claude-opus-5-5')).toBe('Claude Opus 5.5')
    expect(modelDisplayName('claude-sonnet-5-5')).toBe('Claude Sonnet 5.5')
    expect(modelDisplayName('claude-haiku-5-5')).toBe('Claude Haiku 5.5')
    expect(modelDisplayName('claude-opus-5-5-20261001')).toBe('Claude Opus 5.5')
    expect(modelDisplayName('claude-sonnet-4-20250514')).toBe('Claude Sonnet 4')
    expect(modelDisplayName('claude-opus-5')).toBe('Claude Opus 5')
    expect(modelDisplayName('claude-opus-4-1-20250805')).toBe('Claude Opus 4.1')
    expect(modelDisplayName('claude-3-5-sonnet')).toBe('claude-3-5-sonnet')
    expect(modelDisplayName('some-other-model')).toBe('some-other-model')
  })
})
