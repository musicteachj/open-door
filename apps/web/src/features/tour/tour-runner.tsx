import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { useIdentityBusy } from '@/app/useIdentityBusy'
import type { SignedInMe } from '@/app/useMe'
import { CoachMarkHost } from '@/components/tour/coach-mark-host'
import { TourEndCard } from '@/components/tour/tour-end-card'
import { useGetCurrentConversation } from '@/api/generated'
import { useAssistantTexts, useConversationActions } from '@/features/chat/use-conversation'
import { isChatBusy, useChatStore } from '@/features/chat/store'
import { personaFor } from '@/features/personas/personas'
import type { useIdentityActions } from '@/features/shell/use-identity-actions'
import { useShellToast } from '@/features/shell/toast-store'
import { isEndStep, TOUR } from './script'
import { useTourStore } from './store'
import { useTurnFinished } from './use-chip-turn'
import { findTourElements, useTourElements } from './use-tour-elements'

const LEFT_TOAST = 'Tour closed. You can pick it up again from the persona menu.'
/** How long a finished turn must be missing its card or panel before the step says so. */
const MISSING_AFTER_MS = 250
/** How long to wait before asking again for a persona the shell refused to switch to. */
const SWITCH_RETRY_MS = 250

type TourRunnerProps = {
  me: SignedInMe
  /** The shell's identity actions, so the switcher shows its busy state while the tour switches. */
  actions: Pick<ReturnType<typeof useIdentityActions>, 'switchTo'>
  /** "Choose who to be": the shell opens the persona menu. */
  onChoosePersona: () => void
}

const onPath = (pathname: string, path: string) =>
  pathname === path || pathname.startsWith(`${path}/`)

/**
 * Runs the guided tour (screen 15), mounted in the app shell. It makes the visitor the step's
 * persona (the switcher's busy state and the "Now viewing as" toast come from the switch itself),
 * takes them to the step's page, and only then shows the coach mark. A chip is sent through the
 * conversation's own `send`, which says whether the server took the question and gives the turn it
 * made. A step's result counts as shown when that turn (the step's last chip's own) has finished,
 * or, for a step that expects a card or a panel, when one belonging to that turn is on the page; a
 * turn that finished without it, or a send that was taken and left no turn to follow, shows the
 * step's missing line. A send the server never took gives the chip back. Leaving hides the coach
 * mark and keeps the step.
 */
export function TourRunner(props: TourRunnerProps) {
  // Everyone else pays nothing for the tour: the working part (the assistant's texts, the page
  // reads) mounts only while a tour is on. The menu's Resume sets `active`, which mounts it.
  const active = useTourStore((s) => s.active)
  // A step that does not exist (a stale value) renders nothing.
  const known = useTourStore((s) => TOUR[s.step] !== undefined)
  return active && known ? <ActiveTour {...props} /> : null
}

function ActiveTour({ me, actions, onChoosePersona }: TourRunnerProps) {
  // Only mounted while the tour is active (see `TourRunner`), so `active` is not read here.
  const index = useTourStore((s) => s.step)
  const sent = useTourStore((s) => s.sent)
  const entering = useTourStore((s) => s.entering)
  const turnId = useTourStore((s) => s.turnId)
  const lost = useTourStore((s) => s.lost)
  const outcome = useTourStore((s) => s.outcome)
  const visit = useTourStore((s) => s.visit)
  // The store's actions are stable (zustand creates them once), so reading them from the store
  // does not subscribe to its state, and they are safe in dependency lists.
  const tour = useTourStore.getState()
  const def = TOUR[index]!
  const end = isEndStep(index)
  const navigate = useNavigate()
  const { pathname } = useLocation()
  // The same gate `switchTo` refuses on, which also covers a sign out or a sandbox start.
  const { busy: identityBusy } = useIdentityBusy()

  // Entering a step: first the persona, then the page. The coach mark waits for both.
  const personaOk = me.personaKey === def.persona
  // Bumped to run the entering check again after a switch the shell refused (see below).
  const [recheck, setRecheck] = useState(0)
  // The visit the runner already navigated to the step's page for: once per entry, so a route that
  // redirects away from the step's page cannot loop.
  const navigatedFor = useRef<number | null>(null)
  useEffect(() => {
    if (!entering) return
    if (!personaOk) {
      if (identityBusy) return
      // Read now, not rendered: setting it must not re-run this effect before the switch shows
      // busy.
      if (useTourStore.getState().switchTried) {
        // Asked once and nothing is running now, yet the visitor is not the step's persona: the
        // switch failed, or it landed on someone else. Asking again would loop, so the tour is
        // left with its step kept: the shell shows its retry, and Resume from the menu tries again.
        tour.leave()
        return
      }
      // Counted only when the switch really started: a refused one has not been tried.
      if (actions.switchTo(def.persona, { tour: true, to: def.path })) {
        tour.switchAttempted()
        return
      }
      // Refused: another identity change was in flight that this render has not seen yet, so
      // nothing here would run the check again. Look again shortly, once per refusal (never a
      // loop: a later render that sees the change busy returns above).
      const timer = setTimeout(() => setRecheck((n) => n + 1), SWITCH_RETRY_MS)
      return () => clearTimeout(timer)
    }
    if (onPath(pathname, def.path) || navigatedFor.current === visit) {
      // Already there, or taken there once and the page is still not the step's (a redirect): show
      // the step anyway, and the coach mark centers itself when its target is missing.
      tour.arrived()
      return
    }
    navigatedFor.current = visit
    void navigate(def.path)
    // A navigation that leaves the path as it was changes nothing to run this check again.
    const timer = setTimeout(() => tour.arrived(), SWITCH_RETRY_MS)
    return () => clearTimeout(timer)
    // `actions.switchTo` is the shell's and changes with its state: the effect must not re-run on
    // it. The tour's own actions are stable.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [entering, personaOk, pathname, def.path, def.persona, identityBusy, recheck, visit])

  const shown = !entering && personaOk
  const chips = def.chips ?? []
  // A step with no chips (Dana's cases and console) sends nothing, so it reads no conversation.
  const hasChips = chips.length > 0
  const { send, ready } = useConversationActions({ enabled: hasChips })
  const busy = useChatStore(isChatBusy)
  const lastChipSent = chips.length > 0 && sent.includes(chips.length - 1)
  // The step's result is its last chip's own turn: it has finished, or the send was taken and left
  // no turn to follow (it finishes without a result: the missing line and Next). Nothing else
  // counts, not the chat store's global error, nor an earlier turn with the same words.
  const turnFinished = useTurnFinished(lastChipSent ? turnId : null)
  const finished = lastChipSent && (turnFinished || lost)
  const elements = useTourElements(def, lastChipSent ? turnId : null, shown && !end)
  // Only a step that expects a card or a panel counts one as its result, and only one inside its
  // last chip's own turn (marked with the turn's ID), so a card from earlier in the conversation
  // never is, however many there are and whatever else unmounts as the new one appears.
  const present = def.expect !== undefined && lastChipSent && elements.own !== null

  const saved = useGetCurrentConversation({ query: { enabled: shown && hasChips } })
  // The assistant's texts or the conversation could not be read: a chip would wait for ever. The
  // page shows its own error for either, and a chip pressed now is not queued.
  const texts = useAssistantTexts({ enabled: hasChips })
  const unreadable = texts.isError || saved.isError
  const onStepPage = onPath(pathname, def.path)
  // Chips pressed before the assistant’s texts load, or while the
  // last answer is still coming, wait for the conversation to be idle, in the order pressed, for
  // the step they were pressed on. Each chip is queued at most once.
  const [queued, setQueued] = useState<readonly { step: number; chip: number }[]>([])
  const sendChip = (chip: number) => {
    const question = chips[chip]!
    const isLast = chip === chips.length - 1
    // Reports come back for the visit the chip was pressed in, so one that lands after the visitor
    // moved on never touches the next step's chips.
    const { visit } = useTourStore.getState()
    useTourStore.getState().markSent(chip)
    // Only the last chip's turn is waited for: its ID is stored as soon as the server gives it,
    // which is the only place it is stored (the outcome below only confirms it).
    const onAccepted = isLast
      ? (id: string) => useTourStore.getState().setTurnId(visit, id)
      : undefined
    const onIssued = isLast ? () => useTourStore.getState().markIssued(visit) : undefined
    void send(question, undefined, onAccepted, onIssued).then((outcome) => {
      if (outcome.kind === 'not-sent') {
        // The server never took the question (still answering, a refusal, a failure with a
        // response): the chip may be pressed again. "Never sent twice" holds because every other
        // ending keeps the chip Sent.
        useTourStore.getState().unmarkSent(visit, chip)
      } else if (isLast) {
        if (outcome.kind === 'failed-after-accept') useTourStore.getState().sendLost(visit)
      }
    })
  }
  useEffect(() => {
    if (queued.length === 0) return
    if (queued.some((q) => q.step !== index)) {
      setQueued((all) => all.filter((q) => q.step === index))
      return
    }
    if (unreadable) {
      // Nothing was sent, so the chips stay pressable; the page's own error is what shows.
      setQueued([])
      return
    }
    // Pressed on another page: the navigation back is under way, and the conversation view that
    // shows the answer is not mounted yet.
    if (!onStepPage) return
    // Read now, not from the last render: one chip's send makes the chat busy at once, which holds
    // the next one back until its answer is done.
    if (!ready || isChatBusy(useChatStore.getState())) return
    const [next, ...rest] = queued
    setQueued(rest)
    if (!useTourStore.getState().sent.includes(next!.chip)) sendChip(next!.chip)
    // `sendChip` closes over the step's chips, which the queued chips belong to.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [queued, index, ready, busy, unreadable, onStepPage])

  // The step's outcome is latched in the tour store the first time it is known, so leaving the
  // page or starting a new conversation afterward cannot change it. A step without an expected
  // card or panel has its result when its turn finishes; one with it, when its own card or panel
  // is seen. A turn that finished with none is "missing" once that has held for a moment, so the
  // swap from the live turn to its saved copy never flashes the line; a card that shows up later
  // (a re-ask) still makes it a result.
  const wantsCard = def.expect !== undefined
  const absent = wantsCard && finished && !present && outcome === null
  useEffect(() => {
    if (!lastChipSent) return
    if (wantsCard ? present : finished) useTourStore.getState().settle(visit, 'result')
  }, [wantsCard, present, finished, lastChipSent, visit])
  useEffect(() => {
    if (!absent) return
    const timer = setTimeout(
      () => useTourStore.getState().settle(visit, 'missing'),
      MISSING_AFTER_MS,
    )
    return () => clearTimeout(timer)
  }, [absent, visit])

  if (!shown) return null

  const leave = () => {
    tour.leave()
    useShellToast.getState().show(LEFT_TOAST, me.id, 'info')
  }
  const goTo = (to: number) => tour.goTo(to)

  if (end) {
    return (
      <TourEndCard
        persona={personaFor(def.persona).firstName}
        onKeepExploring={tour.end}
        onLeave={leave}
        onChoose={() => {
          tour.end()
          onChoosePersona()
        }}
      />
    )
  }

  const resultShown = chips.length === 0 || outcome !== null
  return (
    <CoachMarkHost
      step={index + 1}
      title={def.title}
      body={def.body}
      chips={chips}
      sent={sent}
      resultShown={resultShown}
      missing={outcome === 'missing' ? def.missing : undefined}
      target={elements.target}
      avoid={[elements.result]}
      blocked={[elements.composer]}
      header={elements.header}
      fallbackFocus={() =>
        // Read now, not from the last frame: the composer may have just mounted.
        findTourElements(def).composer?.querySelector<HTMLElement>('textarea') ??
        document.querySelector<HTMLElement>('main')
      }
      onSend={(chip) => {
        if (sent.includes(chip) || unreadable) return
        // Before the assistant's texts load a send does nothing, and while an answer is still
        // coming a second question is not taken, so the press waits for the conversation to be
        // idle, behind any chip pressed before it.
        // Busy is read now, not from this render: a chip pressed in the same tick as another sees
        // the first one's send.
        if (queued.length === 0 && ready && !isChatBusy(useChatStore.getState()) && onStepPage) {
          sendChip(chip)
          return
        }
        // Off the step's page (the visitor wandered to another one), the answer would stream where
        // nothing shows it: go back to the page first, and send once it is there.
        if (!onStepPage) void navigate(def.path)
        setQueued((all) =>
          all.some((q) => q.chip === chip) ? all : [...all, { step: index, chip }],
        )
      }}
      onBack={() => goTo(index - 1)}
      onNext={() => goTo(index + 1)}
      onSkip={() => goTo(index + 1)}
      onLeave={leave}
    />
  )
}
