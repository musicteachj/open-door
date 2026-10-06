const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * Whether a value from the URL is a UUID. The generated client puts an ID into a URL or a query as
 * it is, so anything else (a path, a query string, "../me") must never reach it, and the API
 * answers 422 to a filter that isn't one.
 */
export function isUuid(value: string): boolean {
  return UUID.test(value)
}
