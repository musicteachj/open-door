import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import {
  getCaseSummary,
  getCaseText,
  getGetCaseQueryKey,
  useGetCase,
  useRetryCaseSummary,
  type CaseDetailOut,
  type CaseSummaryOut,
} from '@/api/generated'
import type { WordsState } from '@/components/cases/case-words-reveal'
import {
  summaryRetryKind,
  summaryStateOf,
  type SummaryState,
} from '@/components/cases/summary-state'
import { ApiError } from '@/lib/api-fetch'

/** How often the page looks again while a summary is being written, and how often its clock ticks. */
export const readTiming = { pollMs: 4000, tickMs: 15_000 }

/** How long a summary the server was asked to write again is waited for before offering a retry. */
const REWRITE_WAIT_MS = 150_000

type Fetched = { caseId: string; summary: CaseSummaryOut | null; failed: boolean }
type Rewrite = { startedAt: number; from: string | null }

/**
 * A case's detail: its metadata (a query: not audited, fine in the cache), and the two audited
 * reads, the AI summary and the person's words. **Those two never touch the query cache:** they are
 * fetched with the plain generated functions and held in this component's state, so a window
 * gaining focus, a reconnect, or a refetch of the metadata can never read them again and write an
 * audit row. The summary is read once per view, when the metadata says one is written (a ref keyed
 * by the case and the summary's own date makes React's StrictMode, which runs effects twice in
 * development, read it once). The words are read on each press of "Show", and dropped on Hide.
 *
 * While the summary is being written, the metadata is looked at again every few seconds (it is
 * the unaudited read), and a clock ticks so a summary still missing after 2.5 minutes offers "Try
 * again". Nothing here is written to the cache: the metadata is read again by invalidation.
 */
export function useCaseDetail(caseId: string, personId: string) {
  const queryClient = useQueryClient()
  const [rewrite, setRewrite] = useState<Rewrite | null>(null)
  const rewriteRef = useRef<Rewrite | null>(null)
  rewriteRef.current = rewrite

  const query = useGetCase(caseId, {
    query: {
      throwOnError: (error, q) =>
        q.state.data === undefined && !(error instanceof ApiError && error.status === 404),
      refetchInterval: (q) =>
        wantsPoll(q.state.data, rewriteRef.current) ? readTiming.pollMs : false,
    },
  })
  const detail = query.data

  // ----- the summary -----
  const [fetched, setFetched] = useState<Fetched | null>(null)
  const requested = useRef<string | null>(null)
  const reads = detail !== undefined && !detail.isOwn && detail.screening !== 'crisis'
  const writtenAt = detail?.summary?.createdAt ?? ''
  const exists = reads && detail?.summary?.status === 'written'
  const marker = `${caseId}|${writtenAt}`

  // Each read has a number, and only the newest one's answer is kept.
  const summaryRead = useRef(0)
  async function readSummary() {
    const mine = ++summaryRead.current
    try {
      const summary = await getCaseSummary(caseId)
      if (mine !== summaryRead.current) return
      setFetched({ caseId, summary, failed: false })
      // The read is on the timeline now ("read the AI summary"): look at the metadata again.
      void queryClient.invalidateQueries({ queryKey: getGetCaseQueryKey(caseId) })
    } catch {
      if (mine !== summaryRead.current) return
      setFetched({ caseId, summary: null, failed: true })
    }
  }

  useEffect(() => {
    if (!exists || requested.current === marker) return
    requested.current = marker
    // A newer summary replaces what was read for the older one.
    setFetched(null)
    void readSummary()
    // `readSummary` is built from `caseId`, which `marker` holds.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exists, marker])

  const mine = fetched?.caseId === caseId ? fetched : null
  // A moving clock, for as long as the summary is waited for.
  const [now, setNow] = useState(() => new Date())

  const rewriting =
    rewrite !== null &&
    (detail?.summary?.createdAt ?? null) === rewrite.from &&
    now.getTime() - rewrite.startedAt < REWRITE_WAIT_MS
  const state: SummaryState | null = !detail
    ? null
    : rewriting
      ? 'pending'
      : summaryStateOf(detail, mine?.summary ?? null, now, mine?.failed ?? false)

  // The clock runs only while the block is pending: a failed or written summary needs none, and a
  // retry that starts makes it pending again.
  const ticking = state === 'pending'
  useEffect(() => {
    if (!ticking) return
    const id = setInterval(() => setNow(new Date()), readTiming.tickMs)
    return () => clearInterval(id)
  }, [ticking])

  const retrySummary = useRetryCaseSummary()
  const retryBusy = useRef(false)
  const [retrying, setRetrying] = useState(false)

  async function retry() {
    if (!detail || retryBusy.current) return
    if (summaryRetryKind(mine?.failed ?? false) === 'refetch') {
      setFetched(null)
      await readSummary()
      return
    }
    retryBusy.current = true
    setRetrying(true)
    try {
      await retrySummary.mutateAsync({ caseId })
    } catch (error) {
      // A refusal ("too soon", or one is already being written) leaves the block pending: a later
      // look offers the retry again. Any other failure leaves it as it was.
      const refused = error instanceof ApiError && error.problem?.type === 'summary-retry-refused'
      if (!refused) {
        retryBusy.current = false
        setRetrying(false)
        return
      }
    }
    setRewrite({ startedAt: Date.now(), from: detail.summary?.createdAt ?? null })
    setNow(new Date())
    retryBusy.current = false
    setRetrying(false)
    void queryClient.invalidateQueries({ queryKey: getGetCaseQueryKey(caseId) })
  }

  // ----- the words -----
  const [wordsState, setWordsState] = useState<{
    caseId: string
    state: WordsState
    text: string
  } | null>(null)
  const [readHere, setReadHere] = useState(false)
  const [relocked, setRelocked] = useState(false)
  const words = wordsState?.caseId === caseId ? wordsState : null
  // Each reveal has a number: a Hide, or a newer reveal, drops the answer of an older one.
  const wordsRead = useRef(0)
  const wordsLoading = useRef(false)

  async function showWords() {
    if (wordsLoading.current) return
    wordsLoading.current = true
    const mine = ++wordsRead.current
    setWordsState({ caseId, state: 'loading', text: '' })
    try {
      const { text } = await getCaseText(caseId)
      if (mine !== wordsRead.current) return
      setWordsState({ caseId, state: 'shown', text })
      setReadHere(true)
      setRelocked(false)
      // The read added a timeline row: read the metadata again to show it.
      void queryClient.invalidateQueries({ queryKey: getGetCaseQueryKey(caseId) })
    } catch {
      if (mine === wordsRead.current) setWordsState({ caseId, state: 'failed', text: '' })
    } finally {
      if (mine === wordsRead.current) wordsLoading.current = false
    }
  }

  const readInTimeline = (detail?.timeline ?? []).some(
    (entry) => entry.kind === 'text_read' && entry.actorPersonId === personId,
  )

  return {
    query,
    detail,
    summary: {
      state,
      text: mine?.summary?.text ?? undefined,
      writtenAt: mine?.summary?.createdAt ?? undefined,
      model: mine?.summary?.model ?? undefined,
      retrying,
      retry,
    },
    words: {
      state: (words?.state ?? 'hidden') as WordsState,
      text: words?.text ?? '',
      show: showWords,
      hide: () => {
        // Whatever is still on its way is not shown.
        wordsRead.current++
        wordsLoading.current = false
        setWordsState({ caseId, state: 'hidden', text: '' })
      },
    },
    /** This person has read the words, in an earlier view (the timeline) or in this one. */
    wordsRead: !relocked && (readHere || readInTimeline),
    /** The server said the words were not read: lock the actions until they are. */
    relock: () => {
      setRelocked(true)
      setReadHere(false)
    },
  }
}

/** Whether the metadata should be looked at again: a summary is being written, within its wait. */
function wantsPoll(detail: CaseDetailOut | undefined, rewrite: Rewrite | null): boolean {
  if (!detail || detail.isOwn || detail.screening === 'crisis') return false
  if (rewrite !== null) {
    return (
      (detail.summary?.createdAt ?? null) === rewrite.from &&
      Date.now() - rewrite.startedAt < REWRITE_WAIT_MS
    )
  }
  return (
    detail.summary?.status === 'none' && Date.now() - Date.parse(detail.sentAt) < REWRITE_WAIT_MS
  )
}
