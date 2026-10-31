import { createContext } from 'react'

/**
 * Who is reading, for the links that are only theirs: a person has My cases and HR has the queue,
 * and neither can open the other's page. Null (the default, and the gallery) allows neither. The
 * conversation page provides it from who is signed in, so the model's words never decide it.
 */
export type AnswerViewer = 'person' | 'hr' | null
export const AnswerViewerContext = createContext<AnswerViewer>(null)
