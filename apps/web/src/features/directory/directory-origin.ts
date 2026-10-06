// Where a profile was opened from, carried in the router's location state so "← Directory" can
// return to the list as the visitor left it. State belongs to one history entry, so it follows
// Back, Forward, and a reload, and a profile opened from a shared link simply has none.

/** `search` is the list's query string ("?q=jo&department=…", or ""); `steps` is how many history
 * entries back that list is: 1 from a row, one more for each manager link followed since. */
export type DirectoryOrigin = { directorySearch: string; steps: number }

/** The state a row's link carries: the list's current search. */
export function fromDirectory(search: string): DirectoryOrigin {
  return { directorySearch: search, steps: 1 }
}

/** The state a link from one profile to another carries: one entry further from the list. */
export function oneStepFurther(origin: DirectoryOrigin | null): DirectoryOrigin | undefined {
  return origin ? { ...origin, steps: origin.steps + 1 } : undefined
}

/** The origin in a location's state, or null when it is missing or not what this module wrote. */
export function originOf(state: unknown): DirectoryOrigin | null {
  if (typeof state !== 'object' || state === null) return null
  const { directorySearch, steps } = state as Partial<DirectoryOrigin>
  if (
    typeof directorySearch !== 'string' ||
    !(directorySearch === '' || directorySearch.startsWith('?'))
  )
    return null
  if (typeof steps !== 'number' || !Number.isInteger(steps) || steps < 1) return null
  return { directorySearch, steps }
}
