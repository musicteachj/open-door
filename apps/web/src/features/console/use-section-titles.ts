import { useCallback, useMemo } from 'react'
import { useHandbookGlance } from '@/features/shell/use-handbook-glance'
import { stateName } from '@/components/handbook/labels'

/**
 * A handbook section's title from its ID, for the console's tiles and traces. An addendum's title
 * adds its state ("Sick leave (California)"), because the same title repeats across states.
 *
 * It shares the shell's non-throwing handbook entry (`useHandbookGlance`), so the console does not
 * download the handbook again. A failure leaves the titles out and the console shows the IDs alone.
 */
export function useSectionTitles(): (sectionId: string) => string | undefined {
  const handbook = useHandbookGlance()
  const titles = useMemo(() => {
    const map = new Map<string, string>()
    for (const section of handbook.data?.sections ?? []) {
      map.set(
        section.id,
        section.kind === 'addendum' && section.addendumState
          ? `${section.title} (${stateName(section.addendumState)})`
          : section.title,
      )
    }
    return map
  }, [handbook.data])
  return useCallback((sectionId: string) => titles.get(sectionId), [titles])
}
