import { describe, expect, it } from 'vitest'
import { cn } from '@/lib/utils'

describe('cn', () => {
  it('joins class names and drops falsy values', () => {
    expect(cn('p-4', false, undefined, 'flex')).toBe('p-4 flex')
  })

  it('lets a later utility of the same kind win', () => {
    expect(cn('p-2', 'p-4')).toBe('p-4')
  })

  it('keeps a type size and a text color together', () => {
    expect(cn('text-small', 'text-ink-muted')).toBe('text-small text-ink-muted')
  })

  it('replaces one type size with another', () => {
    expect(cn('text-small', 'text-body')).toBe('text-body')
  })

  it('treats the focus halo as a shadow, not a shadow color', () => {
    expect(cn('shadow-focus-halo', 'shadow-primary')).toBe('shadow-focus-halo shadow-primary')
    expect(cn('shadow-xs', 'shadow-focus-halo')).toBe('shadow-focus-halo')
  })

  it('knows the design weights, heights, and radii', () => {
    expect(cn('font-regular', 'font-semibold')).toBe('font-semibold')
    expect(cn('font-sans', 'font-semibold')).toBe('font-sans font-semibold')
    expect(cn('h-control', 'h-control-sm')).toBe('h-control-sm')
    expect(cn('rounded-md', 'rounded-lg')).toBe('rounded-lg')
  })

  it('knows every spacing name in the theme', () => {
    expect(cn('w-rail', 'w-panel')).toBe('w-panel')
    expect(cn('w-panel', 'w-content')).toBe('w-content')
    expect(cn('max-w-sidebar', 'max-w-panel')).toBe('max-w-panel')
  })
})
