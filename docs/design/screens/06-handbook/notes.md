# 06 · Handbook and the passage panel

**Phase:** 3 (the passage panel is reused in Phase 4) · **Viewport:** desktop · **Personas:**
everyone; frames as Priya and Mateo

Approved on 2026-10-07, after two rounds. The working frames are in
[`../../system/Handbook.dc.html`](../../system/Handbook.dc.html), the shared panel in
[`../../system/Passage Panel.dc.html`](../../system/Passage%20Panel.dc.html), and the components'
source in [`../../system/components/handbook/`](../../system/components/handbook/). The
screenshots here were rendered from those files.

**Sample data:** the personas and their locations match the seed company. The section list, the
section text, the "Last updated" dates, every figure, and the Sources lines are placeholders for
layout. The real handbook is written, and each statutory figure checked against its official
source, in Phase 3's handbook stage. Only seven sections have body text in the mockup; the rest
say "Sample text for this section isn't written yet." The side-by-side comparison should focus
on layout and states, not on the words.

## Purpose

Anyone at Juniper Row can read the whole handbook, and every policy answer the assistant gives
cites a passage in it. The page has two jobs:

1. **Browse:** find a section and read it, and see at a glance who it applies to and when it last
   changed.
2. **Check a citation:** arrive from a deep link with the cited passage highlighted, so the person
   can check the assistant's work.

The handbook is company-public. Everyone can read every section, including other states'
addenda, and each section says who it applies to. Nothing is hidden or locked.

## Layout

Inside the app shell, with "Handbook" selected.

**Handbook home:** the title "Employee handbook", the meta line ("Juniper Row · Version 2026.10 ·
Updated Sep 12, 2026"), and the demo notice, with the sandbox indicator on the right. Then a
toolbar with the search field and the Show filter. Then the section list, laid out as a table of
contents with three columns (Section, Applies to, Last updated). The company sections are
grouped by chapter, each chapter under a heading row. Then "State addenda" with a one-line
explanation, and one group per state (California, Colorado, Texas), each headed by its code, its
name, and "For California employees". Each row shows the number, the title, the "Applies to"
text, the marker where it applies (see Interactions), the date, and a chevron.

**Section page:** "← Handbook" back to the list, and the sandbox indicator. Then the article, in
the 760 px reading measure at 18/28:

- the eyebrow ("§4.3 · Time off", or "CA-4.3 · California addendum" for an addendum, with no §),
  the title, then the "Applies to" badge, the marker, and "Last updated"
- the demo notice
- for Mateo on a section that doesn't apply to him, a neutral note: "This section is for
  California employees. You work at the Austin warehouse in Texas." and the link "See what
  applies to you: §4.3 Sick leave"
- a link block: "State rules" on a company section that addenda supplement ("California and
  Colorado add to this section.", one row per addendum with its marker), or "Supplements" on an
  addendum ("§4.3 Sick leave · Company handbook")
- the body: headings, paragraphs, and bulleted lists
- on an addendum, a "Sources" block below the body: one line per statutory source, such as
  "California Labor Code §246, read from dir.ca.gov on Oct 6, 2026."
- previous and next cards, in handbook order, which can cross from one addendum into the next

Beside the article, a slim chapter navigator ("Chapter 4 · Time off", or "California addendum")
lists that chapter's sections, with the current one tinted. It stays in place as the page scrolls.

**Passage panel:** a 420 px panel docked on the right of the sheet. On the assistant home it takes
the right rail's place while it's open. From top to bottom:

- the header: the eyebrow ("Handbook CA-4.3 · California addendum", or "Handbook §4.3 · Time off"),
  the close button, the title, the "Applies to" badge, the marker, and "Last updated"
- the body, which scrolls inside the panel: the paragraph before the cited one in muted text, the
  cited passage, and the paragraph after it in muted text
- the footer: "Open in handbook"

The header and footer stay fixed, so a passage of any length fits.

**Narrow screens** (no mockup): the chapter navigator moves above the article or folds away, the
list's columns stack under each row's title, and the panel covers the content instead of sitting
beside it.

## Components used

App shell (Logo, Nav item, Persona switcher), Sandbox indicator, Page header, Search field,
Filter select ("Show"), and from `components/handbook/`:

- **ApplicabilityBadge:** "Applies to: California employees", built by `appliesLabel` from up to
  three parts: everyone, a state, an employment type, or a location ("Hourly staff in
  California").
- **AppliesMarker:** "Applies to you" (a primary check and ink text) or "Doesn't apply to you" (a
  muted dash and muted text).
- **LastUpdated:** "Last updated Sep 12, 2026", in tabular figures.
- **SectionRow** and **SectionGroup**, plus the `.od-sec-nav` chapter navigator.
- **CitedPassage:** the tint, the quote icon and "Cited passage" label, the cinnamon bar, and
  "Clear highlight" on the section page.
- **LinkBlock:** the "State rules" and "Supplements" variants.
- **SourcesBlock**
- **SearchResultRow**
- **PassagePanel:** open, loading, error.

Also Empty state ("No sections match"), Skeleton (static bars, no shimmer), and the full-page
message pattern from the global states.

## States

| State | Screenshot | What differs |
|---|---|---|
| Default | `desktop-default.png` | Priya's handbook home: the list grouped by chapter, with markers only on CA-3.4 and CA-4.3 (below the fold) |
| Section | `desktop-section.png` | Priya on §4.3 Sick leave: "State rules" links to CA-4.3 (marked) and CO-4.3 |
| Cited passage | `desktop-cited-passage.png` | Priya arriving at `/handbook/CA-4.3?passage=p2`: scrolled to the highlighted passage, with "Clear highlight", then Sources and previous and next |
| Doesn't apply | `desktop-not-applicable.png` | Mateo on CA-4.3: "Doesn't apply to you", the neutral note, and "See what applies to you: §4.3 Sick leave" |
| Search | `desktop-search.png` | Mateo searching "overtime": three results, the one that applies to him first, with the matched word emphasized |
| No results | `desktop-no-results.png` | No sections match "dental plan.", with "Clear search" and "Ask the assistant" |
| Loading | `desktop-loading.png` | The list's skeleton rows, keeping the header, toolbar, and column labels |
| Section loading | `desktop-section-loading.png` | The section's skeleton, with the back link kept |
| Missing section | `desktop-missing-section.png` | `/handbook/8.2`: "This section isn't in your handbook version." with "Back to the handbook" |
| Panel states | `desktop-panel-states.png` | The panel open, loading, with an error and Retry, and with a long passage that scrolls (CA-3.3 as Priya, who isn't covered) |
| Panel docked | `desktop-panel-docked.png` | The panel on the assistant home, in the rail's place; the conversation is placeholder blocks until Phase 4 designs it |

## Interactions

- **The marker in the list** appears only on sections with a restricted audience (a state, an
  employment type, or a location) that covers the person. Rows that apply to everyone never carry
  one. For Priya that's CA-3.4 and CA-4.3. **Section pages, search results, and the panel** show
  the marker on every section, "Applies to you" or "Doesn't apply to you".
- **Rows are plain links** in the Tab order with the visible focus ring, as in the directory. The
  list has no arrow-key navigation. A row's accessible name is its number, title, audience, the
  marker where shown, and the date.
- **Search** filters as you type, with no search button. Results list the sections that apply to
  the person first, then by relevance. Each shows its number, title, source (company handbook or
  the addendum), a one-line excerpt with the matched words emphasized, the badge, the marker, and
  the date. The clear button (×) appears once there is text.
- **No results:** "Clear search" empties the field. "Ask the assistant" opens Ask with the search
  text in the composer, not sent.
- **Show:** "All sections" or "Applies to me", a single-choice menu with counts. "Applies to me"
  keeps the sections the person is covered by, everyone's sections included.
- **A deep link** (`/handbook/:sectionId?passage=:passageId`) scrolls the page to the cited
  passage and moves focus to it. The passage is a region labeled "Cited passage", so a screen
  reader announces the label first.
- **"Clear highlight"** removes `?passage` from the URL without adding a history entry, and the
  paragraph returns to plain text.
- **A section ID that isn't in the sandbox's handbook version** shows the missing-section page
  inside the shell, with "Back to the handbook".
- **"State rules" and "Supplements"** link a company section and its addenda both ways. The
  neutral note's "See what applies to you" goes to the company section the addendum supplements.
- **The chapter navigator** marks the current section with `aria-current="page"`.
- **The passage panel isn't modal.** When it opens, focus moves to its title. Escape or the close
  button closes it, and focus returns to the citation that opened it. "Open in handbook" goes to
  the section page with the same passage highlighted, and stays available when the panel shows
  an error. The panel's body scrolls by keyboard too, since it takes focus.
- **Errors stay inline:** "Couldn't load this passage." with Retry in the panel. A failed list or
  section load uses the global "Something went wrong" page.

## Copy

- Title: "Employee handbook"; meta: "Juniper Row · Version 2026.10 · Updated Sep 12, 2026"
- Demo notice: "Juniper Row is a fictional company. This handbook is demo content, not legal
  advice."
- Search placeholder and label: "Search the handbook"; clear button: "Clear search"
- Filter: "Show All sections", "Show Applies to me"
- Column labels: "Section", "Applies to", "Last updated"
- Addenda heading: "State addenda" with "Each addendum section supplements the company section
  with the same number."; groups "California addendum · For California employees", and so on
- Badge: "Applies to: Everyone", "Applies to: California employees", "Applies to: Hourly staff",
  "Applies to: Hourly staff in California"
- Markers: "Applies to you", "Doesn't apply to you"
- Date: "Last updated Sep 12, 2026"
- Section page: "← Handbook"; eyebrows "§4.3 · Time off" and "CA-4.3 · California addendum"
- Link blocks: "State rules" with "California and Colorado add to this section." (or "California
  adds…"); "Supplements" with "§4.3 Sick leave · Company handbook"
- Neutral note: "This section is for California employees. You work at the Austin warehouse in
  Texas." and "See what applies to you: §4.3 Sick leave"
- Cited passage: "Cited passage", "Clear highlight"
- Sources: the heading "Sources", then lines like "California Labor Code §246, read from
  dir.ca.gov on Oct 6, 2026." with no "Source:" prefix
- Previous and next: "Previous", "Next", with the section's number and title
- Search: "3 sections match "overtime"" ("1 section matches…"); empty: "No sections match
  "dental plan."" with "Clear search" and "Ask the assistant"
- Missing: "This section isn't in your handbook version." and "There's no §8.2 in version 2026.10
  of the Juniper Row handbook." with "Back to the handbook"
- Panel: eyebrows "Handbook CA-4.3 · California addendum" and "Handbook §4.3 · Time off"; close
  button "Close passage"; "Open in handbook"; error "Couldn't load this passage." with "Retry"
- Screen-reader only: "Loading the handbook", "Loading section", "Loading passage"

## Acceptance criteria

- [ ] Matches the screenshots at 1440 px, within the component library's spacing tokens
- [ ] Usable at 390 px: the list's columns stack, the navigator moves out of the way, the panel
      covers the content, and nothing overflows
- [ ] The list shows every section of the sandbox's pinned handbook version, grouped by chapter
      and then by addendum, each with its "Applies to" text and "Last updated" date
- [ ] In the list, the marker appears only on restricted sections that cover the person; never on
      an "Everyone" row
- [ ] Section pages, search results, and the panel show "Applies to you" or "Doesn't apply to you"
      on every section, each with its icon, so color is never the only signal
- [ ] Each section page shows its eyebrow, title, badge, marker, "Last updated", the demo notice,
      its "State rules" or "Supplements" block where one applies, and Sources on an addendum
- [ ] A deep link with `?passage=` scrolls to the passage, highlights it, and moves focus to it;
      a screen reader hears "Cited passage" first
- [ ] "Clear highlight" removes `?passage` without adding a history entry
- [ ] A section ID that isn't in the pinned version shows the missing-section page, inside the
      shell
- [ ] Search results put the sections that apply to the person first, then sort by relevance, and
      emphasize the matched words; no results offers "Clear search" and "Ask the assistant", which
      opens Ask with the text in the composer, not sent
- [ ] "Applies to me" keeps exactly the sections that cover the person, and the counts in the menu
      match the list
- [ ] The passage panel opens with focus on its title, closes with Escape or its close button,
      returns focus to the citation, scrolls a long passage inside itself, and shows the inline
      error with Retry
- [ ] The cinnamon bar on the cited passage is decoration: about 2.8:1 against the tint, it
      reinforces the label and quote icon, which carry the meaning
- [ ] The chapter navigator marks the current section with `aria-current="page"`
- [ ] Every control and row is reachable by keyboard with a visible focus ring; axe reports no
      violations

## What the build needs from the API

There's no handbook API yet. This screen needs:

- **the section list** of the sandbox's pinned version: each section's ID, number, title, chapter
  or addendum, audience, and last-updated date, plus the version's label and date
- **one section:** its blocks (headings, paragraphs with stable passage IDs, and lists), its
  audience, the company section it supplements or the addenda that supplement it, and its sources
- **search** over the pinned version, with an excerpt and the matched terms for each result
- **whether each section applies to the signed-in person**, worked out on the server from their
  location and employment type, so the browser never decides it
- **one passage** with the paragraphs before and after it, for the panel

The Phase 3 spec settles the shapes.
