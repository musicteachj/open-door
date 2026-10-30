/**
 * A failed first load goes to the route's error boundary (the "Something went wrong" page), but a
 * read again that fails after data was shown does not replace a page the person is using.
 */
export const onlyFirstLoad = (_error: Error, query: { state: { data: unknown } }) =>
  query.state.data === undefined
