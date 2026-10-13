/**
 * Whether an ID from the URL can be sent as one path segment. Encoding stops it adding a "/" or a
 * query, but "." and ".." come through unchanged, and the URL parser resolves them as steps up
 * the path, to another route.
 */
export function isPathSegment(id: string): boolean {
  return id !== '' && id !== '.' && id !== '..'
}
