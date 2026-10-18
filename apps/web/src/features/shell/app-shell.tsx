import { useEffect, useRef, useState } from 'react'
import { Outlet, useLocation } from 'react-router'
import { Logo } from '@/components/core/logo'
import { Banner } from '@/components/feedback/banner'
import { InlineError } from '@/components/feedback/inline-error'
import { NavItem } from '@/components/navigation/nav-item'
import { PersonaMenu } from '@/components/navigation/persona-menu'
import { GlanceList, type GlanceItem } from '@/components/status/glance-list'
import { SandboxIndicator } from '@/components/status/sandbox-indicator'
import { Toast, ToastProvider, ToastViewport } from '@/components/ui/toast'
import { navFor } from '@/app/nav'
import { useMe } from '@/app/useMe'
import { getGetHandbookQueryKey, useGetHandbook } from '@/api/generated'
import {
  ConversationSourcePanel,
  NARROW_WINDOW_QUERY,
} from '@/features/chat/conversation-source-panel'
import { useSourceUrl } from '@/features/chat/source-url'
import { PERSONAS } from '@/features/personas/personas'
import { useMediaQuery } from '@/hooks/use-media-query'
import { cn } from '@/lib/utils'
import { formatMonthDay, formatTimeLeft, isExpiringSoon } from '@/lib/time'
import { useExpiryBannerDismissal } from './expiry-banner-dismissal'
import { useIdentityActions } from './use-identity-actions'
import { ShellBannerSlot } from './shell-slots'
import { useShellLayout } from './shell-layout-store'
import { useNow } from './use-now'
import { useScrollsMore } from './use-scrolls-more'
import { useShellToast } from './toast-store'

// The signed-in frame, from docs/design/screens/02-app-shell and 03-assistant-home: a sidebar, a
// white content sheet (the page's one <main>), and a right rail. Below 760 px the sidebar becomes
// a top bar with the sandbox indicator, the navigation scrolls sideways, and the rail drops below
// the content. It renders between RequireSession and the routes, so the reset key remounts it.

const COMPANY = 'Juniper Row'
// "How it's built" sits at the bottom of the sidebar, apart from the rest of the navigation.
const BUILT_PATH = '/how-its-built'
// The only page with the right rail (the sandbox status and the at-a-glance list).
const RAIL_PATH = '/ask'
// The balance and pending-request figures arrive with their data in Phase 5.
const PERSONA_OPTIONS = PERSONAS.map(({ key, name, title }) => ({ key, name, title }))

export function AppShell() {
  const { data: me } = useMe()
  if (!me) return null
  return <Frame me={me} />
}

function Frame({ me }: { me: NonNullable<ReturnType<typeof useMe>['data']> }) {
  const actions = useIdentityActions()
  const now = useNow()
  // The right rail belongs to the assistant home alone. Every other page takes the sheet's width.
  const showRail = useLocation().pathname === RAIL_PATH
  // The conversation has its own sandbox pill in its header, so the shell's two (the top bar's and
  // the rail's) step aside, and "At a glance" moves up and hides on a phone (screen 07's notes).
  const conversation = useShellLayout((s) => s.conversation) && showRail
  // A passage open from a citation (`?source=`) takes the rail's place (`w-panel`, 420 px) from
  // 1280 px up. Below that it is a modal sheet instead, over everything. The rail itself stops
  // being a side column at 1100 px.
  const sourceOpen = useSourceUrl().key !== null && showRail
  const narrow = useMediaQuery(NARROW_WINDOW_QUERY)
  const dockedPanel = sourceOpen && !narrow
  // Where a page puts a banner that spans the sheet, the rail included.
  const [bannerSlot, setBannerSlot] = useState<HTMLElement | null>(null)
  const items = navFor(me)
  // Only the rail shows the figure, so only the assistant home asks. A failure leaves it out:
  // the rail is a convenience, not the page.
  // It has its own cache entry: the Handbook page's query throws to the error page, and a failure
  // here must not be left in that entry for the page to find.
  const handbook = useGetHandbook({
    query: { queryKey: [...getGetHandbookQueryKey(), 'glance'], enabled: showRail },
  })
  const glance: GlanceItem[] = handbook.data
    ? [
        {
          id: 'handbook-updated',
          value: formatMonthDay(handbook.data.version.updatedOn),
          label: 'Handbook updated',
          destination: 'Handbook',
          to: '/handbook',
        },
      ]
    : []
  const [navRef, navScrolls] = useScrollsMore<HTMLElement>()
  const [dismissed, dismiss] = useExpiryBannerDismissal(me.tenantExpiresAt)

  const msLeft = Date.parse(me.tenantExpiresAt) - now
  const timeLeft = formatTimeLeft(msLeft)
  const bannerMessage = `This sandbox resets in ${timeLeft}. Everything you've done here will be cleared.`
  const bannerShown = isExpiringSoon(msLeft) && !dismissed

  // The banner's text changes every minute, so it is not a live region. This one is always
  // mounted, and says the banner's words once, when the banner first appears.
  const [announcement, setAnnouncement] = useState('')
  useEffect(() => {
    if (!bannerShown) return
    // Next tick, so the region is in the page, empty, before it gets its words.
    const timer = setTimeout(() => setAnnouncement((said) => said || bannerMessage), 0)
    return () => clearTimeout(timer)
  }, [bannerShown, bannerMessage])

  // After a switch lands, focus is on <body> (the old shell is gone). Put it in the page, so a
  // keyboard or screen-reader user knows where they are. The toast's presence says a switch just
  // landed here: any other reset clears it.
  const mainRef = useRef<HTMLElement>(null)
  useEffect(() => {
    if (useShellToast.getState().personId === me.id) mainRef.current?.focus()
  }, [me.id])

  return (
    <div className="flex min-h-dvh bg-surface text-ink max-[760px]:flex-col">
      <aside
        aria-label="Sidebar"
        className="sticky top-0 flex h-dvh w-sidebar flex-none flex-col pt-7 pr-4 pb-5 pl-5 max-[760px]:static max-[760px]:h-auto max-[760px]:w-auto max-[760px]:px-4 max-[760px]:pt-4 max-[760px]:pb-2"
      >
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-2 pb-8 max-[760px]:px-0 max-[760px]:pb-3">
          <Logo customerName={COMPANY} />
          <SandboxIndicator
            className={cn('hidden max-[760px]:inline-flex', conversation && 'max-[760px]:hidden')}
          >
            Sandbox resets in {timeLeft}
          </SandboxIndicator>
        </div>

        <nav
          ref={navRef}
          aria-label="Main"
          data-more={navScrolls}
          className="flex flex-col gap-0.5 max-[760px]:flex-row max-[760px]:overflow-x-auto max-[760px]:data-[more=true]:[mask-image:linear-gradient(to_right,var(--color-ink)_calc(100%-40px),transparent)]"
        >
          {items
            .filter((item) => item.to !== BUILT_PATH)
            .map((item) => (
              <NavItem
                key={item.to}
                icon={item.icon}
                label={item.label}
                to={item.to}
                className="max-[760px]:shrink-0"
              />
            ))}
        </nav>

        <div className="flex-1 max-[760px]:hidden" />
        {items
          .filter((item) => item.to === BUILT_PATH)
          .map((item) => (
            <NavItem
              key={item.to}
              icon={item.icon}
              label={item.label}
              to={item.to}
              className="mb-3 max-[760px]:hidden"
            />
          ))}

        <PersonaMenu
          personas={PERSONA_OPTIONS}
          currentKey={me.personaKey}
          onSwitch={actions.switchTo}
          onSignOut={actions.signOut}
          busyLabel={actions.busyLabel}
        />
        {actions.failure && (
          <InlineError message={actions.failure.message} onRetry={actions.failure.again} />
        )}
      </aside>

      <ToastProvider>
        <div className="min-w-0 flex-1 p-sheet pl-0 max-[760px]:px-2 max-[760px]:pt-0">
          <div
            data-slot="shell-sheet"
            className={cn(
              'relative flex min-h-[calc(100dvh-24px)] flex-col rounded-xl border border-border bg-surface-raised',
              // `clip` clips the rounded corners without making the sheet a scroll container, so
              // the conversation's header and composer can stick to the window.
              conversation ? 'overflow-clip' : 'overflow-hidden',
            )}
          >
            <output data-slot="shell-announcement" className="sr-only">
              {announcement}
            </output>
            {bannerShown && <Banner live={false} message={bannerMessage} onDismiss={dismiss} />}
            <div data-slot="shell-banner-slot" ref={setBannerSlot} />
            <div
              className={cn(
                'grid min-h-0 flex-1',
                showRail
                  ? 'grid-cols-[minmax(0,1fr)_var(--spacing-rail)] max-[1100px]:grid-cols-1 max-[1100px]:grid-rows-[1fr_auto] max-[760px]:grid-cols-1'
                  : 'grid-cols-1',
                dockedPanel && 'grid-cols-[minmax(0,1fr)_var(--spacing-panel)]',
              )}
            >
              <main ref={mainRef} tabIndex={-1} className="flex min-w-0 flex-col outline-none">
                <ShellBannerSlot value={bannerSlot}>
                  <Outlet />
                </ShellBannerSlot>
              </main>
              {dockedPanel ? (
                <ConversationSourcePanel docked />
              ) : (
                showRail && (
                  <aside
                    aria-label="Sandbox status"
                    className={cn(
                      'flex flex-col border-l border-border-subtle bg-surface-sunken px-8 pt-7 pb-8 max-[1100px]:border-t max-[1100px]:border-l-0',
                      // Below 760 px the indicator is in the top bar, so with no glance items the
                      // rail would be an empty strip. The conversation hides it there too.
                      (glance.length === 0 || conversation) && 'max-[760px]:hidden',
                    )}
                  >
                    {!conversation && (
                      <div className="flex justify-end">
                        <SandboxIndicator className="max-[760px]:hidden">
                          Sandbox resets in {timeLeft}
                        </SandboxIndicator>
                      </div>
                    )}
                    <GlanceList
                      items={glance}
                      className={conversation ? 'mt-1' : 'mt-16 max-[1100px]:mt-6'}
                    />
                  </aside>
                )
              )}
            </div>
            {sourceOpen && narrow && <ConversationSourcePanel docked={false} />}
            <ShellToast personId={me.id} />
          </div>
        </div>
      </ToastProvider>
    </div>
  )
}

/** Shows the toast only to the person it is about, whatever else is in the store. */
function ShellToast({ personId }: { personId: string }) {
  const { message, personId: forPerson, id, clear } = useShellToast()
  return (
    <>
      {message && forPerson === personId && (
        <Toast
          key={id}
          defaultOpen
          onOpenChange={(open) => {
            if (!open) clear()
          }}
        >
          {message}
        </Toast>
      )}
      <ToastViewport className="absolute" />
    </>
  )
}
