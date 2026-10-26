import { describe, expect, it } from 'vitest'

// A write that finishes after a persona switch must not put the old person's answer into the new
// person's cache, so hooks read again (`invalidateQueries`) and never set data. The one exception
// is `signInAs`, which stores the new person's own `/me` right after it clears the cache.
const sources = import.meta.glob<string>(['/src/**/*.ts', '/src/**/*.tsx'], {
  query: '?raw',
  import: 'default',
  eager: true,
})

describe('the query cache', () => {
  it('is set by one file only: the one that signs a person in', () => {
    const setters = Object.entries(sources)
      .filter(([path]) => !path.includes('.test.') && !path.endsWith('/api/generated.ts'))
      .filter(([, source]) => /setQueryData|setQueriesData/.test(source))
      .map(([path]) => path)
    expect(setters).toEqual(['/src/app/useMe.ts'])
  })
})
