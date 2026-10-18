import { createContext } from 'react'

/**
 * The source key of the passage open in the panel, if any. Only the markers and chips read it (to
 * say whether theirs is the open one), so opening or closing the panel redraws those and not the
 * turns around them.
 */
export const OpenSourceContext = createContext<string | null>(null)
