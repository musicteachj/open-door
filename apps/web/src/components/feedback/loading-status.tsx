import { useEffect, useRef } from 'react'

type LoadingStatusProps = {
  loading: boolean
  /** What is loading, as a screen reader hears it: "Loading the profile". */
  text: string
}

/**
 * A polite status that says what is loading, as the directory table does. The region is always in
 * the page and its text is written in an effect, because a live region announces changes made
 * after it is mounted, not text that arrives with it. React renders it with no children, so
 * writing through the ref doesn't fight a render.
 */
function LoadingStatus({ loading, text }: LoadingStatusProps) {
  const ref = useRef<HTMLOutputElement>(null)
  useEffect(() => {
    if (ref.current) ref.current.textContent = loading ? text : ''
  }, [loading, text])
  return <output data-slot="loading-status" ref={ref} className="sr-only" />
}

export { LoadingStatus }
