import { useEffect, useState } from 'react'

const MINUTE_MS = 60_000

/** The current time in milliseconds, refreshed every minute, so a countdown re-renders as it runs. */
export function useNow(intervalMs: number = MINUTE_MS): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])
  return now
}
