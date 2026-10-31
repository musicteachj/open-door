import { AI_TAG } from './labels'

/** The small bordered "AI" mark. Decoration: the words beside it say who wrote what. */
function AiTag() {
  return (
    <span
      aria-hidden="true"
      className="inline-flex h-5 items-center rounded-xs border border-border-strong bg-surface-raised px-1.5 text-[11px]/4 font-semibold tracking-[0.03em] text-ink"
    >
      {AI_TAG}
    </span>
  )
}

export { AiTag }
