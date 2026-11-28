# 0025. Gentle motion shows that the app is working

Status: Accepted · Date: 2026-11-28

## Context

The design system allowed color and border transitions only: "Nothing moves", skeleton bars were
static with no shimmer, and the spinner was the only animation. Dialogs, menus, and toasts appeared
and vanished instantly, and the session gate, the landing page, and the Ask page were blank while
they loaded.

Trying the app, the owner asked a question on the Ask page and could not tell whether the assistant
was working, and the answer then appeared all at once. Two things caused it:

- In production nothing visible arrives while the safety check runs and the model thinks, which
  can take several seconds. The page showed only a static gray caret. In development the scripted
  model sends its first step at once, so this never showed there.
- When the model writes its answer, makes one more tool call, and then ends with nothing more to
  say, the server takes the text back as a working note and sends it again as one piece.

## Decision

Add a small amount of motion, all of it opacity, and all of it off under `prefers-reduced-motion`
(the existing rule in `base.css`, which stops every animation and transition):

- **Fades:** 150 ms in, 100 ms out, on new status steps, dialogs, menus, toasts, and items that
  arrive late in the shell. Selects fade in only, because Radix unmounts their list at once on
  close. Tooltips stay instant: they already wait 300 ms to open,
  and a fade-out left a tooltip that is closed and reopened at once (leaving its trigger and
  coming straight back) unable to show again. The question, the answer, and the escalation panel
  don't fade: a turn is drawn again as it settles and is saved, and a fade would replay each time,
  a blink at the end of every answer.
- **A soft pulse** on skeleton bars (opacity down to 0.55 and back, 1.6 s).
- **A blinking caret** while the answer is being written.
- **A paced reveal** of the answer's text in the browser, carried on by turn when the turn is drawn
  again (live, settling, saved). Normal streaming looks the same, and a
  large piece is played out over about half a second instead of landing at once. With reduced
  motion, the text appears as it arrives.
- **Steps from the first moment:** the assistant shows "Reading your question…" with a spinner as
  soon as the question is sent, until the server's first real step replaces it, and "Still working
  on it…" if no text has come after 8 seconds.
- **A visible loader** (a spinner and "Loading…", shown after 300 ms so a fast load shows nothing)
  wherever a page used to be blank, and a skeleton for the Ask page.

The design notes in `docs/design/` point here where they said otherwise.

## Rejected alternatives

- **A motion library (Motion, `tw-animate-css`):** a dependency for four keyframes the theme can
  define itself.
- **A gradient shimmer on skeletons:** busier than a pulse, and it needs colors outside the theme
  tokens.
- **Slides, scaling, bounce, page transitions:** they move content the reader is looking at, and
  the design's calm tone rules them out.
- **Fixing the one-piece answer on the server** (sending the restored text in small pieces): it
  fixes only that one path and touches the assistant loop. The browser's reveal covers every burst.
- **A server step during the safety check:** more exact, but it changes the turn stream and its
  tests. The browser's first step says only what is true: the question is being read.

## Consequences

- No server, prompt, or eval change, so no paid eval run.
- Only a burst is paced: a piece of 48 characters or fewer shows at once, so ordinary streaming
  doesn't re-render the answer on every frame.
- Confirm cards and the HR panel don't wait for the reveal. They sit beside the message, not in
  it, and the text catches up within half a second.
- Tests that asserted "no animation" on skeletons now assert the pulse sits behind `motion-safe`.
- The browser tests' accessibility scan reduces motion while it runs, so a fade that starts as late
  data arrives is never read mid-blend.
- The browser tests that check reduced motion still hold: every new class is behind
  `motion-safe:`, and the reduced-motion rule stops them anyway.
