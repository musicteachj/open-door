# Screen 16 · The recorded walkthrough

**Phase:** 8 · **Viewport:** desktop · **Personas:** a visitor, signed in or not

Approved on 2026-11-09, in one round. The working frames are in
[`../../system/Walkthrough.dc.html`](../../system/Walkthrough.dc.html), and the landing's additions
in [`../../system/Landing.dc.html`](../../system/Landing.dc.html). Replay mode is this page
([ADR 0019](../../../adr/0019-replay-mode-is-a-recorded-walkthrough.md)); the
[Phase 8 spec](../../../specs/2026-11-05-phase-8-hardening-and-deploy-readiness.md) has the
detail.

- A public page at `/walkthrough`: no sign-in, no persona, no app navigation. It shows the guided tour (screen 15), recorded once with the live assistant, and its transcript.
- Offered in two places: the landing ("Watch the recorded walkthrough") and the assistant's limit-reached state, when the demo's daily AI limit pauses the assistant until tomorrow (that link is not drawn here).
- Source: `Walkthrough.dc.html`. The landing additions are also applied to `Landing.dc.html` (frame 1a).
- `poster-sample.png` is screen 15's step 1 answer frame (1440 × 900), standing in for a frame of the recording. The real poster comes from the recording. Answers are sample text; the real transcript comes from the recording.

## Frames

| File | What it shows |
| --- | --- |
| desktop-landing | Screen 01 as it is now, with "Watch the recorded walkthrough" beside the tour button and the Cloudflare line under the sandbox note |
| desktop-walkthrough | Header, heading, intro, the paused video, the metadata line, "Transcript" with steps 1 and 2, the footer (the transcript is cut after step 2 for the frame) |
| desktop-walkthrough-transcript | The same page scrolled to steps 3 to 7 |

## Copy

- Landing link: "Watch the recorded walkthrough". Landing line: "Starting a sandbox runs a quick Cloudflare check to keep the demo safe."
- Header: "Back to the demo". Heading: "The recorded walkthrough". Intro: "The guided tour, recorded with the live assistant: the same ten steps you can take yourself."
- Metadata (sample values): "Recorded October 26, 2026 · Claude Opus 5.5 · 2 min 30 s · No sound"
- Steps: the brief's text verbatim (label, persona line, title, coach mark words, questions, answers, sources, notes).
- Step 10 has no coach mark words in the brief; it uses the end card's first paragraph from screen 15: "You've seen answers that change by state and always cite the handbook, a day off requested and approved on cards a person confirmed, private details kept private, a sensitive concern sent to HR in the person's own words, and a record of everything the AI did." Its second paragraph ("This sandbox stays for 24 hours…") is left out, since the page has no sandbox.

### Copy not given in the brief

- Speaker labels: the person's first name ("Priya"); the AI's answer label "AI" badge plus "Open Door", as in the conversation view; "HR panel" with "Fixed text written by a person, not the AI".
- "Source" before each cited section.
- Accessible names: "Play the recorded walkthrough" (poster play button), "Open Door home" (logo link), "Open Door, the AI assistant" (hidden text in each answer label).

## Layout

- Page: `--surface`, 136 px side padding, one 1168 px column, as on the landing. Header 72 px.
- Heading block: 56 px below the header; 760 px measure; 12 px between heading and intro.
- Video: 40 px below the intro, full column width (1168 × 730 at 16:10), `--border` edge, `--radius-lg`. Metadata 12 px below.
- Transcript: 80 px below the metadata, 760 px measure, left-aligned to the column. "Transcript" h2, then each step as an `article` with a `--border` rule on top, 40 px above its content and 48 px below.
- Inside a step: step label, 4 px, title, 12 px, persona line, 20 px, coach mark words, 24 px, the exchange box, 16 px, the note.
- Exchange box: `--surface-raised`, `--border`, `--radius-lg`. Each row is a 152 px label column and the text, 24 px gap, 20 × 24 px padding, `--border-subtle` between rows. The HR panel's row is on `--surface-sunken`.
- Footer: as on the landing, 88 px above it.

## Type

- Heading: `--text-h1` 28/36, 600, `--tracking-h1`. Intro: `--text-body-lg` 18/28, ink-muted.
- "Transcript" and step titles: `--text-h2` 20/28, 600.
- Coach mark words: 16/26, ink (the handbook reads at 18/28; this sits between body and handbook text).
- Questions and answers: `--text-body` 15/24, ink, as in the conversation view. Speaker names 14/24, 600.
- Step label, metadata, sources: `--text-small` 13/20. Notes: `--text-ui` 14/20, ink-muted. Persona line: 14/20, name 600 ink, role and location ink-muted. HR panel sub-label: `--text-caption` 12/16, ink-muted.
- All figures use tabular numbers.

## Tokens used

- Color: `--surface`, `--surface-raised`, `--surface-sunken`, `--neutral-hover`, `--ink`, `--ink-nav`, `--ink-muted`, `--on-primary`, `--primary`, `--primary-hover`, `--primary-tint`, `--border`, `--border-subtle`, `--border-strong`, `--focus-ring`. No new tokens.
- Radius: `--radius-xs` (AI badge), `--radius-sm` (back link), `--radius-md` (tour button), `--radius-lg` (video, exchange box, persona cards).
- Icons, none new: `arrow-left`, `play`, `volume-x`, `maximize`, `book-open`, `users`, `check`, `info`, `circle-play`, `map-pin`, `arrow-right`.

## Decisions the build must follow

- The landing link is a text link (14/20, 600, primary, underlined), placed to the left of the tour button, so the button keeps the row's right edge. The Cloudflare line is a second line under the sandbox note in the same style. Nothing else on the landing changes.
- "Back to the demo" goes to the landing (`/`). It's a quiet ink link with `arrow-left`, a `--neutral-hover` fill on hover, no underline. The logo also links to the landing.
- Video: a native `<video controls preload="none" poster>` at 16:10, width 100% of the column. The drawn play button and controls bar stand in for the browser's own; don't build custom controls. No autoplay. The file has no audio track, and the metadata line says "No sound".
- The transcript is the text alternative for the video (WCAG 1.2.1, video-only). Put it in the page as text, not behind a toggle, and keep it in step order.
- Headings: h1 page, h2 "Transcript", h3 for each step title. Each step is an `article` labeled by its title, with an id (`step-3`) so steps can be linked.
- Each exchange is a `dl`: the speaker is the `dt`, the words are the `dd`. AI answers always carry the "AI" badge and "Open Door" label, with the hidden "Open Door, the AI assistant". The HR panel's text is never labeled as the AI's.
- Sources are plain text ("CA-4.3 · Sick leave"), not links or buttons, so they don't look like chips that open a panel. The page has no sign-in, so the handbook isn't reachable from here.
- Notes about what the person did sit under the exchange box in ink-muted with a check. They are not styled as success or as part of the AI's answer.
- Steps without questions (8, 9, 10) show the label, persona line (none on step 10), title, and coach mark words; step 8 adds its note. No empty exchange box.
- No sticky header, no progress or chapter UI, no syncing the transcript to the video.
- Red appears nowhere on this page.

## Accessibility

- Contrast: ink on surface 15.3:1, on white 16.4:1; ink-muted on surface 5.7:1, on white 6.1:1; primary link on surface 10.5:1; white on ink (play button, controls) 16.4:1.
- Focus rings: 2 px `--focus-ring` on the logo link, back link, landing link, and play button (3 px offset on the play button so it shows against the poster).
- The persona avatars are `aria-hidden`; the name follows in text.

## Phone (390 px, notes only)

- 20 px side padding. Header keeps the logo and "Back to the demo".
- The video stays full width at 16:10 under the intro.
- Exchange rows stack: the speaker label above the words, 4 px apart, 16 px padding.
- The landing's bottom row stacks: the two muted lines, then the tour button and the walkthrough link, left-aligned.

## Where the data comes from

- **The video, its poster, and the transcript** come from the recording (`make walkthrough`, Phase
  8 Stage 9): `apps/web/public/media/walkthrough.mp4`, `walkthrough-poster.jpg`, and
  `walkthrough.json`. The page renders the transcript from that file, so its words always match
  the video. Every answer drawn here is a sample.
- **The metadata line** (date, model, length) comes from `walkthrough.json`.
- **The steps' labels, titles, persona lines, and coach mark words** come from the tour's own
  script (`apps/web/src/features/tour/script.ts`), recorded into the same file.
- **The sample day** is screen 15's, Monday, October 26, 2026: Priya has 92 hours of PTO before
  step 3 (the poster) and 84 after booking 8 hours, and Zara Bautista's request is for November 9
  and 10 (screen 09).

## Build decisions (owner, 2026-11-09)

These were decided after the handoff. Where they differ from a screenshot or the notes above, the
build follows this section, and the screenshots are not redrawn.

- **The poster is a frame from the recording with nothing important under its center,** since the
  browser's own play button may sit there. In `desktop-walkthrough` the drawn play button covers
  the coach mark's words.
- **"Back to the demo" returns the visitor to where they came from** inside Open Door (for example
  the conversation that reached the daily limit), and to the landing (`/`) when they arrived from
  outside or opened the page directly. The notes above say it always goes to the landing.
- **The video is `preload="none"`** (as the notes above say; the plan had said `metadata`), so a
  visitor who never presses play downloads nothing beyond the poster.
- **The step's title comes before its persona line,** as drawn (the prompt had the persona line
  first).
- **Step 10's words are the end card's first paragraph** from screen 15, as Claude Design chose.
- **The daily-limit banner's link isn't drawn here:** it is a link under the banner's existing,
  approved text, built from the existing banner and checked in the capture report.

## Acceptance criteria

- [ ] Matches the screenshots at 1440 px, within the component library's spacing tokens
- [ ] Usable at 390 px, as the phone notes above describe; the video stays 16:10 and full width
- [ ] `/walkthrough` works without a session, and has no app navigation or persona
- [ ] The video uses the browser's own controls, never autoplays, and has a poster
- [ ] The transcript is real text in step order, one `article` per step with an `h3` title and an
      id (`step-3`); each exchange is a `dl`; every answer carries the AI label, and the HR panel's
      text never does
- [ ] Sources are plain text, not links or chips
- [ ] "Back to the demo" follows the build decision above
- [ ] The landing shows the walkthrough link left of the tour button and the Cloudflare line under
      the sandbox note; nothing else on the landing changes
- [ ] The daily-limit banner shows the walkthrough link; the sandbox-limit banner doesn't
- [ ] axe is clean, and every focusable element shows the focus ring
