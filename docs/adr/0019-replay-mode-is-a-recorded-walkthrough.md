# 0019. At the daily limit, the demo offers a recorded walkthrough, not replayed model calls

Status: Accepted · Date: 2026-11-05

## Context

The design spec says that when the global daily AI budget is reached, "the demo switches to a
replay mode built on the recorded fixtures, so it never goes dark". The Phase 4 spec narrowed it to
"replay mode, the recorded walkthrough", and the design brief's banner reads "Demo budget reached,
showing a recorded walkthrough". Since Phase 4, reaching the limit disables the composer and shows
the owner's approved text; the handbook, the directory, and the other pages keep working.

Three facts decide what "replay" can mean here:

- **The recorded fixtures can't answer a live sandbox.** A fixture is keyed by a hash of the exact
  request. Every request carries the sandbox's own dates (today, "next Friday", accrued balances),
  people IDs, and conversation, so a new sandbox's requests never match a recording.
- **Keying recordings by the question instead would show wrong facts.** A recorded answer to
  "Book next Friday off." names a past Friday, and a recorded balance disagrees with the page
  beside it. The confirm card would propose dates the engine refuses.
- **The app refuses the replay transport** (CLAUDE.md: "replay is for the eval harness only"), so
  the recordings stay a test of the graders and the plumbing, never something a visitor reads as
  the assistant's answer.

## Decision

- **Replay mode is the recorded walkthrough.** When today's demo limit is reached, the banner keeps
  its approved text and adds a link, "Watch the recorded walkthrough". It opens a walkthrough page:
  the demo video, a text transcript of every step, and the date and model it was recorded with.
  Everything that doesn't need the model stays live: time off, approvals, cases, the handbook, the
  directory, and the console.
- **The video is the demo video.** It is recorded locally with Playwright from the guided tour's
  own script, against the real model (Opus 5.5, the pinned prompt), through the production image.
  It is silent: the tour's coach marks carry the words on screen, and the transcript repeats them
  for anyone who can't watch. It is converted to MP4 (H.264) with ffmpeg, kept under 8 MB, and
  committed with a poster image, so the production image serves it from its own origin and the
  README links it.
- **The walkthrough page is public,** like the landing, so it works without a sandbox and a
  reviewer can choose to watch instead of trying. Screen 16 designs it and where the landing
  offers it; the banner's link sits under the banner's existing text.
- **It is re-recorded only when the tour or the screens it shows change visibly,** each time with
  the owner's OK as a paid run, and the page always says when it was recorded.

## Rejected alternatives

- **Replaying recorded model calls in the sandbox:** every request misses, for the reasons above,
  and making it work would mean an app path for the eval-only transport.
- **Recordings keyed by the tour's question:** stale dates and figures beside live pages, and cards
  the engine refuses.
- **The scripted model at the limit:** its answers are written by hand, so showing them as the
  assistant's answers would mislead (invariant 7 says the assistant is an AI; a person's text in
  its place isn't).
- **Doing nothing ("try again tomorrow"):** the demo goes dark for the AI, which is what a
  reviewer came to see.

## Consequences

- The design spec's "built on the recorded fixtures" is superseded by this record; the frozen
  initial plan stays as written. CLAUDE.md's rule that the app refuses `replay` stands.
- The repository holds one small binary that changes rarely. Each re-recording adds a new copy to
  the history, so it stays under 8 MB and is re-recorded only for visible changes.
- The owner-approved budget text is unchanged; the link is a separate element under it, so its
  hash and approval stand. The link's words and the transcript are approved with screen 16.
- A silent video with a full text transcript meets WCAG 2.2's success criterion 1.2.1 for
  prerecorded video-only media. The player never autoplays.
