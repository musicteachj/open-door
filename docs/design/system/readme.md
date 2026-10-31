# Open Door design system

Open Door is an AI-first HR help desk: employees ask HR questions in plain language and get answers that cite the company handbook. The assistant proposes actions and a person confirms them. Sensitive topics (harassment, medical) go to a human HR partner, never the AI. Managers approve requests; HR works a queue of confidential cases. The assistant is the home screen; other pages are for browsing and hand-offs.

Tagline: "Your open-door policy, now always open."

The demo customer is Juniper Row, a fictional 120-person apparel and home retailer (Denver HQ, Oakland CA store, Austin TX warehouse). Visitors explore a private 24-hour sandbox as one of four personas: Priya Raman (Visual Merchandiser, salaried), Mateo Alvarez (Warehouse Associate, hourly), Marcus Bell (Store Manager), Dana Whitfield (HR Business Partner).

Build target: React, Tailwind CSS v4, shadcn/ui (Radix) restyled with these tokens, Lucide icons. Desktop at 1440 px; layouts collapse on phones. Light theme first; token names are semantic so a dark theme can override them. WCAG 2.2 AA.

Sources: everything here was designed in this project. The decision record is `Assistant Home.dc.html` (turns 1 to 4; the final screen is option 4a, foundations 4j). Palette: "aubergine and cinnamon", Wada Sanzo's A Dictionary of Color Combinations, combination 172.

## Index

- `styles.css`: entry point; `@import`s every token and component stylesheet. Link this one file.
- `tokens/`: `colors.css`, `typography.css`, `spacing.css`, `radius.css`, `elevation.css`, `motion.css`, `fonts.css`, `shadcn.css` (shadcn variable aliases), `base.css` (element defaults).
- `components/core/`: Button, Icon, Logo.
- `components/navigation/`: NavItem (with waiting count), PersonaSwitcher (with busy state), PersonaMenu, Tooltip.
- `components/assistant/`: Composer, InlineError, TryAskingRow, TryAskingList.
- `components/status/`: GlanceLink, GlanceList, SandboxIndicator.
- `components/landing/`: PersonaCard (and the od-persona-grid layout class).
- `components/forms/`: SearchField, FilterSelect, FilterToggle.
- `components/directory/`: DirectoryTable, DirectoryRow, SkeletonRow, DetailList, DetailRow.
- `components/feedback/`: Toast, Banner, FullPageMessage (plus .od-icon-btn and .od-text-link helpers).
- `components/handbook/`: ApplicabilityBadge (with appliesLabel), AppliesMarker, LastUpdated, SectionRow and SectionGroup (plus the .od-sec-nav chapter navigator), CitedPassage, LinkBlock (State rules, Supplements), SourcesBlock, SearchResultRow, PassagePanel.
- `components/timeoff/`: StatusBadge, SegmentedControl, ChoiceGroup, HoursStepper, DateField, DatePicker (with CalendarDay, longDate, shortDate), BalanceCard (plus .od-source-chip), RequestRow and RequestGroup, PreviewBlock, FormMessage.
- `components/console/`: ConsoleTile, TurnTable (with SafetyLabel, InjectionTag), TracePanel, Scoreboard (with ScoreboardSetRow).
- `components/tour/`: CoachMark (with TourRing), TourChip, TourEndCard, TourMenuItems (with TourStartDialog).
- `ui_kits/assistant/`: app shell and assistant home for Priya.
- `App Shell.dc.html`: screen 02, persona menu, switching, per-persona navigation, expiry banner.
- `Global States.dc.html`: screen 05, session expired, not found, something went wrong.
- `Directory.dc.html`: screen 04, Directory list and profile pages with their states.
- `Handbook.dc.html`: screen 06, handbook home, section page, cited passage deep link, search, states, and the passage panel docked on the assistant home.
- `Passage Panel.dc.html`: the shared passage panel (open, loading, error), imported by Handbook and Conversation.
- `Conversation.dc.html`: screen 07, the conversation view (/ask): cited answers, source panel, streaming, feedback, escalation and crisis panels, errors, budget banners, composer notices. Screenshots and notes are in `screen-07-conversation/`.
- `Time Off.dc.html`: screen 08, Time off (/time-off): balances, schedule, the request form and date picker, My requests, cancel, and page states. Screenshots and notes are in `screen-08-time-off/`; the standalone export is `screen-08-time-off/Time Off.html`.
- `Landing.dc.html`: screen 01, Try Open Door (landing page with persona picker and its states).
- `AI Ops Console.dc.html`: screen 13, the AI Ops console (/console, HR only): sandbox tiles, the turn list, the docked trace panel, and page states. Screenshots and notes are in `screen-13-ai-ops-console/`; components in `components/console/`.
- `Scoreboard.dc.html`: the AI Ops console's eval scoreboard, made self-contained.
- `Guided Tour.dc.html`: screen 15, the ten-step guided tour: coach marks, persona switching, leaving and resuming, the end card, and the persona menu's tour items. Screenshots and notes are in `screen-15-guided-tour/`; components in `components/tour/`.
- `guidelines/`: foundation specimen cards (colors, type, spacing, radius, shadows, focus, logo, icons).
- `assets/`: `logo-mark.svg` (32 px master), favicons (`favicon.svg`, `favicon-16.svg`, `favicon-16.png`, `favicon-32.png`, `apple-touch-icon.png` at 180, `icon-512.png`), `logo-explorations/` (round 1 candidates), `fonts/` (Instrument Sans, Geist Mono, self-hosted woff2).
- `preview/loader.js`: preview-only helper so cards and kits render without a build.
- `SKILL.md`: agent skill entry point.

Each component has `Name.jsx`, `Name.d.ts` (props contract) and `Name.prompt.md` (when to use, example). Components use `od-` class names defined in each folder's CSS; pass `data-state="hover"` or `"focus"` to render a state statically in documentation.

### Intentional additions

- Icon: wraps the Lucide glyphs in use so specimens render without a package; production uses lucide-react with the same names.
- Tooltip: split out of the persona switcher so other truncated text can reuse it.
- TryAskingList and GlanceList: the labeled containers the rows sit in on the home screen.

## Content fundamentals

- Voice: calm, plain, specific American English. Sounds like a good HR partner: direct, kind, never chirpy.
- Address the reader as "you". The product speaks about itself in the third person ("Open Door is an AI assistant").
- Sentence case everywhere: buttons, nav, headings. No Title Case and no all caps.
- No exclamation points, emoji, "oops", or jokes. Nothing cute near sensitive topics.
- Be specific: "11.5 days PTO available", "Sandbox resets in 21 h", "Handbook updated Sep 12". Prefer numbers and dates over adjectives.
- Buttons are verbs that say what happens: "Ask", "Confirm", "Edit dates", "Withdraw request", "Retry".
- Errors say what happened without blame and offer the next step: "Something went wrong sending that." plus Retry. A denied request is a decision, written neutrally, never styled as an error.
- Suggested questions are written as an employee would ask them: "How many sick days do I get?", "Book next Friday off", "Who do I talk to about a concern?"
- The AI disclosure is always visible in the composer: "Open Door is an AI assistant. It can make mistakes, and it always shows its sources."
- Greeting: "Good morning, Priya." (morning, afternoon, evening by local time).

## Visual foundations

- Feel: quiet confidence, closer to good banking or healthcare software than a social app. Neutrals do most of the work; color appears only when it means something.
- Color: cool porcelain neutrals (surface #F5F7F8, white content sheet, slate ink #14212A). Aubergine primary #59256A for actions, links, selection, and focus. Pale lilac tint #ECE2F0 for the selected nav item and hovered rows. Cinnamon #C27544 is a marker only (the pending-request dot), never text, always beside a word. Red #B42318 is for errors only.
- Text on tint is always ink, never primary.
- Type: Instrument Sans throughout. 600 weight for the 48 px greeting, headings, buttons, and figures; 400 for body. All numbers use tabular figures. Geist Mono only for code and token values.
- Layout: 248 px sidebar on the porcelain background; a white content sheet inset 12 px with a 16 px radius; on the home screen a 340 px right rail in surface-sunken. Content measure 760 px. Generous top padding (120 px) above the greeting. 4 px spacing scale.
- Borders over shadows. Sheets and cards use decorative borders (#DDE3E6, #E8ECEE). Text fields use input-border #7F8C93 (3.5:1, WCAG 1.4.11), darkening to #5E6B73 on hover. Shadows are limited to a 1 px composer shadow, a soft popover shadow, and the composer focus halo.
- Radius: 10 px for buttons, nav, rows; 14 px composer; 16 px sheet; 6 px tooltip; full for avatar and the sandbox pill. No pill buttons.
- Hover: one step darker fill for filled buttons; neutral gray (#ECEFF1) for nav and the persona switcher so hover never reads as selected; primary tint for list rows and at-a-glance links, whose destination label also underlines.
- Focus: 2 px aubergine outline, 2 px offset, via :focus-visible, on every control including destructive ones. The composer shows focus with a primary border and a 3 px halo.
- Press: no shrink or bounce. Color and border transitions only, 150 ms, standard easing; disabled under prefers-reduced-motion.
- Disabled: #E7EBED fill with #87939A text. The Ask button stays enabled when the box is empty and moves focus to the box instead.
- No gradients, textures, illustrations, cartoon people, confetti, or blur. Imagery is not part of the product UI.
- Privacy: private fields the viewer can't see render as calm locked rows (muted lock plus who can see it), never blurred or redacted values, and never in warning colors.
- Navigation per persona: everyone gets Ask, Time off, Directory, Handbook; managers add Approvals with a waiting count; HR adds Cases and Console; the persona switcher sits at the bottom.
- Time off: balances read as a ledger that adds up to the figure, never a chart. Request statuses pair a glyph with the word (cinnamon clock for waiting, success check for approved, ink cross for denied, success clipboard for recorded, muted slash for canceled). Warnings in forms use the amber tint and never block; refusals use the red tint and disable submit. Open Door never asks why someone wants time off.
- Approvals: one card per waiting PTO request with facts only (dates, amount, available after, sent, team coverage) and Approve and Deny. Never a score, ranking, warning color, or suggestion, and no bulk approve. Sick time is never decided. Approve and Deny carry equal weight: both secondary on the card, and each dialog confirms with the standard primary button. No red on the screen except real errors. No pronouns: "Zara will see it on the Time off page."
- Confirm cards: the AI proposes, a person decides. Every time-off action in the conversation is a ConfirmCard under a one-line reply: engine facts, sources, "Proposed by the AI. Nothing happens until you confirm.", Confirm (primary on every variant) and Dismiss (never "Cancel", so it can't be mistaken for "Cancel time off"). Executed ends on a calm apricot line (`--apricot-tint`) and a status badge; every other ending says "Nothing was changed." and mutes the facts. Never "booked" or "done" while pending.
- Confidential cases: only a person opens a case, never the AI. "Open a confidential case" sits in the HR panel (primary on the sensitive panel, secondary after the crisis text) and on My cases. The form and its sent line sit on --confidential-tint with a lock: quiet, never an alert style, no apricot moment. Red only for the form's errors and a failed send. My cases shows category, sent date, status, and a date line, never the words, and rows aren't links.
- HR case work: the queue shows facts only (person, category, sent, reply, status), sorted by reply date and nothing else. The detail labels the AI summary as the AI's and keeps the person's words behind a recorded reveal; status changes wait until the words have been read. Overdue replies and crisis routing are stated as neutral facts, never warnings. No severity, priority, risk, or recommendation anywhere.
- Notices: toasts confirm (bottom right, auto-dismiss); banners warn about the session (top of the sheet, neutral background, colored icon only); errors stay inline; full-page messages handle expired, not found, and server errors with one action and no illustration.
- Loading: static skeleton bars in surface-hover, no shimmer.
- Applicability: every handbook section carries one "Applies to" label (Everyone, a state, an employment type, a location, or combined). "Applies to you" is a primary check plus ink text; "Doesn't apply to you" is a muted minus plus muted text, never a warning. In the section list only the yes marker shows, and only on restricted sections (a state, an employment type, or a location) that cover the person.
- Citations: the cited paragraph sits on primary tint with ink text, labeled "Cited passage" with a quote icon and a slim cinnamon bar on its left edge. Deep links scroll to it and move focus to it.
- Reading: handbook body text is 18/28 in the 760 px measure; h2 20/28.
- Color is never the only signal: the pending marker sits beside "request pending", errors pair an icon with text, links name their destination.

## Iconography

- Lucide (lucide.dev), outline style, 1.75 stroke, round caps and joins. In production use lucide-react; `components/core/Icon.jsx` holds the same geometry for specimens.
- Sizes: 18 px in nav, 16 px in buttons and rows, 14 px beside 13 px text, 13 px in the sandbox pill.
- Icons inherit text color (ink, ink-nav, or ink-muted); the destination chevron on glance links is primary.
- In use: plus and minus (hours stepper), calendar-minus (skipped day), chevron-left and chevron-right (month), chevron-up (open date field), circle-x (denied), ban (canceled), message-circle (Ask), calendar (Time off), users (Directory), book-open (Handbook), code (How it's built), info (AI disclosure), clock (sandbox), circle-alert (errors), rotate-ccw (Retry), chevrons-up-down (persona switcher), chevron-right (glance links), arrow-right (Ask, Try asking rows), trash-2 (destructive), map-pin (persona location), loader-circle (starting spinner), circle-play (tour), search, x (clear), chevron-down (filters), check (selected option, pressed toggle), lock (private details), arrow-left (back), eye (audit note), clipboard-check (Approvals), folder-lock (Cases), layout-dashboard (Console), log-out (Sign out), triangle-alert (warning banner), circle-check (success toast), quote (cited passage), minus (doesn't apply to you), info (demo notice).
- No emoji, no unicode symbols as icons, no icon font.
- Logo: `assets/logo-mark.svg`, a door ajar in a 32 px aubergine tile with a 9 px radius: a surface-colored doorway with a thin jamb and head, and the leaf swung inward as an aubergine wedge, light showing on the latch side. Two token colors only (primary, surface); tile 10.3:1 on surface, 11.1:1 on surface-raised. At 16 px use `favicon-16.svg`, drawn on whole pixels. Lockups: stacked in the sidebar ("Open Door" 16 px 600 over the customer name 12 px ink-muted), or inline as "Open Door · Juniper Row" (name 600 ink, dot and customer 400 ink-muted, 8 px gaps). Decision record: `Logo.dc.html` option 1a.

## Tokens

All tokens are CSS custom properties on `:root`; see `tokens/*.css` for values with a one-line comment each. `tokens/shadcn.css` maps shadcn's variable names (background, foreground, primary-foreground, accent, input, ring, destructive, radius) to Open Door tokens. Note: shadcn's `--accent` is its hover fill and points at the primary tint; the brand accent color is `--marker`.
