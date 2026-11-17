import { describe, expect, it } from 'vitest'
import { backTarget, walkthroughState } from './walkthrough-back'

describe('backTarget', () => {
  it.each([
    ['/ask?c=abc', '/ask?c=abc'],
    ['/cases/123#notes', '/cases/123#notes'],
    ['/', '/'],
  ])('follows an in-app path: %s', (from, expected) => {
    expect(backTarget({ from })).toBe(expected)
  })

  it.each([
    ['no state', null],
    ['undefined', undefined],
    ['a string', '/ask'],
    ['no from', { other: '/ask' }],
    ['a number', { from: 3 }],
    ['another site', { from: '//evil.example/ask' }],
    ['a full URL', { from: 'https://evil.example/' }],
    ['a backslash trick', { from: '/\\evil.example' }],
    // URL parsing drops tabs and newlines, so each of these would become `//evil.example`.
    ['a tab trick', { from: '/\t/evil.example' }],
    ['a newline trick', { from: '/\n/evil.example' }],
    ['a carriage return trick', { from: '/\r/evil.example' }],
    ['a control character', { from: '/ask\u0000' }],
    ['a space', { from: '/ /evil.example' }],
    ['a relative path', { from: 'ask' }],
    ['the walkthrough itself', { from: '/walkthrough' }],
    ['the walkthrough with a query', { from: '/walkthrough?x=1' }],
    ['the walkthrough with a hash', { from: '/walkthrough#step-3' }],
    // The router matches paths whatever their case, so these are the walkthrough too.
    ['the walkthrough in capitals', { from: '/Walkthrough' }],
    ['the walkthrough in capitals, below', { from: '/WALKTHROUGH/x' }],
    ['the walkthrough percent-encoded', { from: '/walk%74hrough' }],
    ['a path that does not decode', { from: '/ask%E0%A4%A' }],
  ])('goes to the landing for %s', (_label, state) => {
    expect(backTarget(state)).toBe('/')
  })

  it('keeps a page whose name only starts like the walkthrough', () => {
    expect(backTarget({ from: '/walkthroughs' })).toBe('/walkthroughs')
  })
})

describe('walkthroughState', () => {
  it('keeps the path, the query, and the hash', () => {
    expect(walkthroughState({ pathname: '/ask', search: '?c=1', hash: '#end' })).toEqual({
      from: '/ask?c=1#end',
    })
  })
})
