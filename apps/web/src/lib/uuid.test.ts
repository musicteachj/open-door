import { describe, expect, it } from 'vitest'
import { isUuid } from './uuid'

describe('isUuid', () => {
  it('accepts a UUID in either case', () => {
    expect(isUuid('00000000-0000-4000-8000-000000000001')).toBe(true)
    expect(isUuid('9F8B1C2A-0D3E-4F5A-8B6C-7D8E9F0A1B2C')).toBe(true)
  })

  it.each([
    '',
    'abc',
    'loc-1',
    'not-a-uuid',
    '../me',
    '00000000-0000-4000-8000-00000000000',
    '00000000-0000-4000-8000-0000000000012',
    ' 00000000-0000-4000-8000-000000000001',
  ])('refuses %j', (value) => {
    expect(isUuid(value)).toBe(false)
  })
})
