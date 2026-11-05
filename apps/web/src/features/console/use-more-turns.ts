import { useRef, useState } from 'react'
import { listConsoleTurns, type ConsoleTurnOut, type ConsoleTurnsPageOut } from '@/api/generated'

type More = {
  /**
   * The first page these follow. A first page whose data changed is a new object, which drops them.
   */
  after: ConsoleTurnsPageOut
  items: ConsoleTurnOut[]
  cursor: string | null
}

const NONE: ConsoleTurnOut[] = []

/**
 * The pages after the first. The first page is a query; later pages are read on demand and held
 * here. They are dropped when the first page's data changes, because its rows may no longer line
 * up with them. A read that finds the same data keeps them: TanStack Query hands back the same
 * object then. A failed read says so and keeps the button.
 */
export function useMoreTurns(firstPage: ConsoleTurnsPageOut | undefined) {
  const [more, setMore] = useState<More | null>(null)
  const [loading, setLoading] = useState(false)
  // The first page the last failed read followed. A new first page drops the message with the
  // pages: it belonged to them.
  const [failedAfter, setFailedAfter] = useState<ConsoleTurnsPageOut | null>(null)
  // The state is read from the render closure, so a second click before the page draws again
  // would pass it. The ref is current at once.
  const loadingRef = useRef(false)
  const mine = more && more.after === firstPage ? more : null
  return {
    // A stable array when nothing is held, so what is memoized on it holds.
    items: mine?.items ?? NONE,
    nextCursor: mine ? mine.cursor : (firstPage?.nextCursor ?? null),
    loading,
    failed: failedAfter !== null && failedAfter === firstPage,
    load: async (cursor: string) => {
      if (loadingRef.current || !firstPage) return
      loadingRef.current = true
      setLoading(true)
      setFailedAfter(null)
      try {
        const page = await listConsoleTurns({ cursor })
        setMore({
          after: firstPage,
          items: [...(mine?.items ?? []), ...page.items],
          cursor: page.nextCursor,
        })
      } catch {
        setFailedAfter(firstPage)
      } finally {
        loadingRef.current = false
        setLoading(false)
      }
    },
  }
}
