import { useLayoutEffect, useMemo } from 'react'
import { useNavigate } from 'react-router'
import { useIdentityBusy } from '@/app/useIdentityBusy'
import { useMe } from '@/app/useMe'
import { useGetConsoleMetrics, useListConsoleTurns } from '@/api/generated'
import { ConsoleError } from '@/components/console/console-error'
import { ConsoleTiles } from '@/components/console/console-tiles'
import { ConsoleTraceHost } from '@/components/console/console-trace-host'
import { PageHeader } from '@/components/core/page-header'
import { Scoreboard } from '@/components/scoreboard/scoreboard'
import { isScoreboard } from '@/components/scoreboard/types'
import { Button } from '@/components/ui/button'
import generated from '@/generated/scoreboard.json'
import { NotFound } from '@/features/global-states/pages'
import { requestIdOf } from '@/features/global-states/errors'
import { useShellLayout } from '@/features/shell/shell-layout-store'
import { useTourStore } from '@/features/tour/store'
import { PageSandboxIndicator } from '@/features/shell/page-sandbox-indicator'
import { useMoreTurns } from './use-more-turns'
import { useSectionTitles } from './use-section-titles'

// HR's AI Ops console at /console, from docs/design/screens/13-ai-ops-console: what the assistant
// did on every turn in this sandbox, never who asked or what they wrote. Only HR sees it: anyone
// else gets the Not found page.

const consoleCopy = {
  title: 'AI Ops console',
  intro:
    'What the assistant did on every turn in this sandbox. It never shows who asked or what they wrote.',
  section: 'This sandbox',
  loadMore: 'Show more turns',
  loadMoreFailed: 'More turns couldn’t be loaded. Please try again.',
  scoreboardUnavailable: 'The eval scoreboard can’t be shown right now.',
} as const

/**
 * The eval scoreboard from the generated file. The file's shape is checked here, when the console
 * is shown, and not when the module loads: the router imports this page eagerly, so a throw at load
 * would break the whole app. A bad shape leaves one plain line in its place (CI's test of the real
 * file is what catches it before a release).
 */
export function ScoreboardSection({ data }: { data: unknown }) {
  const board = useMemo(() => (isScoreboard(data) ? data : null), [data])
  if (board === null) {
    return (
      <p className="m-0 border-t border-border-subtle pt-10 text-ui text-ink-muted max-[640px]:pt-8">
        {consoleCopy.scoreboardUnavailable}
      </p>
    )
  }
  return (
    <Scoreboard data={board} className="border-t border-border-subtle pt-10 max-[640px]:pt-8" />
  )
}

/**
 * The list's and the tiles' read options. A failed read shows in the section (with Retry), not on
 * the route's error page: the scoreboard below it is still worth reading. No read again on window
 * focus or a reconnect: a changed first page drops the held "Show more" pages and closes a trace
 * open on one. The tiles match, so they never count turns the list does not show.
 */
const CONSOLE_QUERY = {
  throwOnError: false,
  refetchOnMount: 'always',
  refetchOnWindowFocus: false,
  refetchOnReconnect: false,
} as const

export function ConsolePage() {
  const { data: me } = useMe()
  if (!me) return null
  if (!me.isHrAdmin) return <NotFound />
  return <Console timeZone={me.location.timezone} />
}

function Console({ timeZone }: { timeZone: string }) {
  const navigate = useNavigate()
  const { busy } = useIdentityBusy()
  // The docked trace sticks in the window, so the shell's sheet clips instead of scrolling.
  const setStickyPanel = useShellLayout((s) => s.setStickyPanel)
  useLayoutEffect(() => {
    setStickyPanel(true)
    return () => setStickyPanel(false)
  }, [setStickyPanel])
  const turns = useListConsoleTurns(undefined, { query: CONSOLE_QUERY })
  const metrics = useGetConsoleMetrics({ query: CONSOLE_QUERY })
  const more = useMoreTurns(turns.data)
  const sectionTitle = useSectionTitles()

  // Only a load that has nothing to show is an error. A background read that fails keeps the rows,
  // the held pages, and the open trace.
  const failed = (turns.isError && !turns.data) || (metrics.isError && !metrics.data)
  const loading = !failed && (!turns.data || !metrics.data)
  const firstPage = turns.data?.items
  const heldPages = more.items
  const rows = useMemo(() => [...(firstPage ?? []), ...heldPages], [firstPage, heldPages])
  const readAgain = () => {
    void turns.refetch()
    void metrics.refetch()
  }

  const scoreboard = <ScoreboardSection data={generated} />
  const heading = (
    <h2 id="console-sandbox-heading" className="m-0 text-h2">
      {consoleCopy.section}
    </h2>
  )

  const columnClassName = 'px-12 pt-10 pb-12 max-[760px]:px-5 max-[760px]:pb-8'
  const header = (
    <>
      <PageHeader title={consoleCopy.title} right={<PageSandboxIndicator />} />
      <p className="m-0 mt-2 max-w-170 text-[16px]/[26px] text-pretty text-ink-muted">
        {consoleCopy.intro}
      </p>
    </>
  )

  if (failed) {
    return (
      <div className={columnClassName}>
        <div className="w-full max-w-270">
          {header}
          <div className="mt-10">
            <section aria-labelledby="console-sandbox-heading">
              {heading}
              <div className="mt-4 rounded-lg border border-border">
                <ConsoleError
                  reference={
                    requestIdOf(
                      (turns.data ? null : turns.error) ?? (metrics.data ? null : metrics.error),
                    ) ?? undefined
                  }
                  onRetry={readAgain}
                />
              </div>
            </section>
            <div className="mt-16">{scoreboard}</div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <ConsoleTraceHost
      header={header}
      columnClassName={columnClassName}
      turns={rows}
      timeZone={timeZone}
      sectionTitle={sectionTitle}
      loading={loading}
      onAskQuestion={() => void navigate('/ask')}
      onTakeTour={() => useTourStore.getState().setStartDialogOpen(true)}
      tourDisabled={busy}
      before={
        <section
          aria-labelledby="console-sandbox-heading"
          aria-busy={loading || undefined}
          className="flex flex-col gap-4"
        >
          {heading}
          <ConsoleTiles metrics={metrics.data} loading={loading} sectionTitle={sectionTitle} />
        </section>
      }
      after={
        <div className="flex flex-col gap-16">
          {(more.failed || (more.nextCursor !== null && !loading)) && (
            <div className="-mt-4 flex flex-col items-start gap-3">
              {more.failed && (
                <p role="alert" className="m-0 text-ui text-ink-muted">
                  {consoleCopy.loadMoreFailed}
                </p>
              )}
              {more.nextCursor !== null && (
                <Button
                  variant="secondary"
                  loading={more.loading}
                  onClick={() => void more.load(more.nextCursor!)}
                >
                  {consoleCopy.loadMore}
                </Button>
              )}
            </div>
          )}
          {scoreboard}
        </div>
      }
    />
  )
}
