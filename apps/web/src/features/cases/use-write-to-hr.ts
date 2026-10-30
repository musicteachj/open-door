import { useMe } from '@/app/useMe'
import { WRITE_TO_HR_LINK } from '@/components/cases/labels'
import type { AnswerViewer } from '@/components/assistant/answer-viewer'
import type { PageLink } from '@/lib/page-link'

/**
 * The "Write to HR" link for the pages that offer it, or null. HR has no My cases page, so HR is
 * never given one, and nobody is until we know who is asking.
 */
export function useWriteToHrLink(): PageLink | null {
  const { data: me } = useMe()
  return me && !me.isHrAdmin ? WRITE_TO_HR_LINK : null
}

/** Who is reading answers, for the links that belong to one side (see `AnswerViewerContext`). */
export function useAnswerViewer(): AnswerViewer {
  const { data: me } = useMe()
  if (!me) return null
  return me.isHrAdmin ? 'hr' : 'person'
}
