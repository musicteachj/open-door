import { useEffect, useRef, useState } from 'react'

/**
 * Whether a horizontally scrolling element has more to show to its right, for the navigation's
 * edge fade. Re-measured on scroll, and when the element or the window changes size.
 */
export function useScrollsMore<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [more, setMore] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => setMore(el.scrollLeft + el.clientWidth < el.scrollWidth - 1)
    measure()
    el.addEventListener('scroll', measure, { passive: true })
    window.addEventListener('resize', measure)
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => {
      el.removeEventListener('scroll', measure)
      window.removeEventListener('resize', measure)
      observer.disconnect()
    }
  }, [])
  return [ref, more] as const
}
